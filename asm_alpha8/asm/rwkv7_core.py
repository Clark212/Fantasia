from __future__ import annotations

import importlib.util
import json
import math
import os
import re
from pathlib import Path
import time
from typing import Any, List, Mapping

from .encoder import ConceptEncoder
from .language_core import (
    LanguageCore, LanguageGenerationResult, LanguageProposal, LanguageReadResult,
    validate_language_proposal,
)


class RWKV7LanguageCore(LanguageCore):
    """
    Optional real RWKV-7 backend for ASM.

    It follows the official ChatRWKV pip-package API: RWKV(model=..., strategy=...)
    plus PIPELINE(..., "rwkv_vocab_v20230424"). Model weights are intentionally
    not bundled in ASM. The backend only becomes ready when the `rwkv` package
    and a local RWKV-7 checkpoint are available.

    Alpha.2 uses RWKV as a learned recurrent reader/embedding source. Structured
    proposal extraction remains disabled here until a later constrained-extractor
    stage, so no generated text is silently treated as a fact.
    """

    name = "rwkv7"
    native_passthrough = False

    def __init__(
        self,
        encoder: ConceptEncoder,
        *,
        model_path: str | Path,
        strategy: str = "cpu fp32",
        tokenizer: str = "rwkv_vocab_v20230424",
        embedding_dims: int = 128,
        chunk_len: int = 128,
        max_new_tokens: int = 96,
        temperature: float = 0.8,
        top_p: float = 0.5,
        extract_proposals: bool = True,
        extractor_max_tokens: int = 160,
    ):
        self.encoder = encoder
        self.model_path = str(model_path or "").strip()
        self.strategy = str(strategy)
        self.tokenizer_name = str(tokenizer)
        self.embedding_dims = max(16, int(embedding_dims))
        self.chunk_len = max(1, int(chunk_len))
        self.max_new_tokens = max(1, int(max_new_tokens))
        self.temperature = float(temperature)
        self.top_p = float(top_p)
        self.extract_proposals = bool(extract_proposals)
        self.extractor_max_tokens = max(32, int(extractor_max_tokens))
        self.model = None
        self.pipeline = None
        self._load_error: str | None = None
        self._ready = False
        self._load()

    @staticmethod
    def runtime_available() -> bool:
        return importlib.util.find_spec("rwkv") is not None

    def _load(self) -> None:
        try:
            if not self.runtime_available():
                raise RuntimeError("rwkv package is not installed")
            if not self.model_path:
                raise RuntimeError("rwkv model path is not configured")
            path = Path(self.model_path)
            if not path.exists() and not Path(self.model_path + ".pth").exists():
                raise FileNotFoundError(self.model_path)

            # Must be set before importing the package for RWKV-7 models.
            os.environ.setdefault("RWKV_V7_ON", "1")
            os.environ.setdefault("RWKV_JIT_ON", "1")
            os.environ.setdefault("RWKV_CUDA_ON", "0")
            from rwkv.model import RWKV
            from rwkv.utils import PIPELINE

            model_arg = self.model_path[:-4] if self.model_path.endswith(".pth") else self.model_path
            self.model = RWKV(model=model_arg, strategy=self.strategy)
            self.pipeline = PIPELINE(self.model, self.tokenizer_name)
            self._ready = True
            self._load_error = None
        except Exception as exc:
            self.model = None
            self.pipeline = None
            self._ready = False
            self._load_error = f"{type(exc).__name__}: {exc}"

    def _run_tokens(self, tokens: List[int], state=None):
        if not self._ready or self.model is None:
            raise RuntimeError(self._load_error or "RWKV-7 backend is not ready")
        out = None
        remaining = list(tokens)
        while remaining:
            batch = remaining[: self.chunk_len]
            remaining = remaining[self.chunk_len :]
            out, state = self.model.forward(batch, state)
        return out, state

    def _state_embedding(self, state) -> List[float]:
        # Pool recurrent state tensors into a deterministic bounded vector. This
        # is not a separately trained sentence-embedding head; it is an RWKV
        # recurrent-state representation exposed to ASM for later ANN work.
        try:
            import torch
        except Exception as exc:
            raise RuntimeError("torch required for RWKV state embedding") from exc

        values: List[float] = []
        for item in (state or []):
            if isinstance(item, torch.Tensor):
                flat = item.detach().float().reshape(-1).cpu()
                if flat.numel() == 0:
                    continue
                stride = max(1, flat.numel() // 64)
                sampled = flat[::stride][:64].tolist()
                values.extend(float(x) for x in sampled)
        if not values:
            return [0.0] * self.embedding_dims

        vec = [0.0] * self.embedding_dims
        for i, value in enumerate(values):
            vec[i % self.embedding_dims] += math.tanh(float(value))
        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 0:
            vec = [x / norm for x in vec]
        return vec

    def _complete(self, prompt: str, *, max_new_tokens: int, temperature: float, top_p: float) -> str:
        if not self._ready or self.pipeline is None or self.model is None:
            raise RuntimeError(self._load_error or "RWKV-7 backend is not ready")
        tokens = [int(x) for x in self.pipeline.encode(prompt)]
        logits, rnn_state = self._run_tokens(tokens, None)
        out_tokens: List[int] = []
        occurrence = {}
        for _ in range(max(1, int(max_new_tokens))):
            adjusted = logits.clone()
            for token_id, count in occurrence.items():
                adjusted[token_id] -= 0.35 + 0.25 * count
            token = int(self.pipeline.sample_logits(
                adjusted,
                temperature=float(temperature),
                top_p=float(top_p),
            ))
            logits, rnn_state = self.model.forward([token], rnn_state)
            out_tokens.append(token)
            occurrence[token] = 1 + occurrence.get(token, 0)
            current = self.pipeline.decode(out_tokens)
            if "\n\n" in current or current.rstrip().endswith("</json>"):
                break
        return self.pipeline.decode(out_tokens).strip()

    @staticmethod
    def _extract_json_blob(text: str):
        raw = str(text).strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.I)
        raw = re.sub(r"\s*```$", "", raw)
        if "<json>" in raw:
            raw = raw.split("<json>", 1)[1].split("</json>", 1)[0]
        starts = [i for i in (raw.find("["), raw.find("{")) if i >= 0]
        if not starts:
            raise ValueError("extractor returned no JSON")
        start = min(starts)
        decoder = json.JSONDecoder()
        obj, _end = decoder.raw_decode(raw[start:])
        return obj

    @classmethod
    def _proposals_from_extractor_output(cls, text: str) -> List[LanguageProposal]:
        payload = cls._extract_json_blob(text)
        if isinstance(payload, dict):
            payload = payload.get("proposals", [])
        if not isinstance(payload, list):
            raise ValueError("extractor JSON must be a list or {proposals:[...]}")
        proposals: List[LanguageProposal] = []
        for item in payload[:12]:
            if not isinstance(item, dict):
                continue
            proposal = LanguageProposal(
                kind=str(item.get("kind", "")),
                payload=dict(item.get("payload", {})) if isinstance(item.get("payload", {}), dict) else {},
                confidence=float(item.get("confidence", 0.0)),
                source="rwkv7:constrained_extractor",
                evidence=[str(x)[:256] for x in item.get("evidence", [])[:4]] if isinstance(item.get("evidence", []), list) else [],
            )
            valid, _reason = validate_language_proposal(proposal)
            if valid:
                proposals.append(proposal)
        return proposals

    @staticmethod
    def _extractor_prompt(text: str) -> str:
        return (
            "You are a constrained perception module for ASM. You may only PROPOSE interpretations; "
            "ASM will validate them. Return JSON only inside <json>...</json>. "
            "Allowed kinds: belief, nested_belief, drive, self_outcome. "
            "belief payload={holder,proposition_text,polarity}; "
            "nested_belief payload={path:[holder1,holder2(,holder3)],proposition_text,polarity}; "
            "drive payload={holder,kind:goal|fear|expectation,proposition_text,priority}; "
            "self_outcome payload={task_family,strategy,success,score}. "
            "If none are clearly stated, return an empty list. Do not infer unstated facts. "
            "Each item also needs confidence in [0,1] and optional evidence strings copied from the input.\n"
            f"INPUT: {text}\n<json>"
        )

    def _extract_proposals(self, text: str) -> List[LanguageProposal]:
        if not self.extract_proposals:
            return []
        output = self._complete(
            self._extractor_prompt(text),
            max_new_tokens=self.extractor_max_tokens,
            temperature=0.2,
            top_p=0.25,
        )
        try:
            return self._proposals_from_extractor_output(output)
        except Exception:
            return []

    def read(self, text: str) -> LanguageReadResult:
        if not self._ready or self.pipeline is None:
            raise RuntimeError(self._load_error or "RWKV-7 backend is not ready")
        started = time.perf_counter()
        tokens = [int(x) for x in self.pipeline.encode(text)]
        _out, state = self._run_tokens(tokens, None)
        embedding = self._state_embedding(state)
        proposals = self._extract_proposals(text)
        return LanguageReadResult(
            text=text,
            backend=self.name,
            tokens=[str(x) for x in tokens],
            embedding=embedding,
            proposals=proposals,
            elapsed_ms=(time.perf_counter() - started) * 1000.0,
            metadata={
                "learned_reader": True,
                "architecture": "rwkv-7",
                "attention_free": True,
                "weights_frozen": True,
                "proposal_extraction": "constrained_json_v1" if self.extract_proposals else "disabled",
                "state_embedding": True,
            },
        )

    def _state_prompt(self, state: Mapping[str, Any], instruction: str) -> str:
        attention = state.get("attention", {}) if isinstance(state, Mapping) else {}
        internal = state.get("internal", {}) if isinstance(state, Mapping) else {}
        focus = attention.get("epicenter") if isinstance(attention, Mapping) else None
        confidence = internal.get("confidence") if isinstance(internal, Mapping) else None
        instruction = instruction.strip() or "Respond concisely to the current situation."

        context = {
            "focus": focus,
            "internal_confidence": confidence,
            "self_beliefs": state.get("beliefs", {}),
            "agent_beliefs": list(state.get("agent_beliefs", []))[:8],
            "goals": list(state.get("goals", []))[:6],
            "world_states": list(state.get("world_states", []))[:8],
            "relevant_memories": [
                {
                    "event_id": x.get("event_id", x.get("id")),
                    "text": str(x.get("text", ""))[:240],
                    "relevance": x.get("relevance"),
                }
                for x in list(state.get("relevant_memories", []))[:4]
                if isinstance(x, Mapping)
            ],
            "workspace": list(state.get("workspace", []))[:12],
        }
        context_json = json.dumps(context, ensure_ascii=False, separators=(",", ":"))
        if len(context_json) > 6000:
            context_json = context_json[:6000]
        return (
            "User: You are the language surface for ASM, not its belief authority. "
            "Use the supplied cognitive context but do not invent persistent facts or silently modify memory. "
            f"Instruction: {instruction}\n"
            f"ASM_CONTEXT_JSON: {context_json}\n\n"
            "Assistant:"
        )

    def generate(self, state: Mapping[str, Any], *, instruction: str = "") -> LanguageGenerationResult:
        if not self._ready or self.pipeline is None:
            raise RuntimeError(self._load_error or "RWKV-7 backend is not ready")
        prompt = self._state_prompt(state, instruction)
        text = self._complete(
            prompt,
            max_new_tokens=self.max_new_tokens,
            temperature=self.temperature,
            top_p=self.top_p,
        )
        if "\n\n" in text:
            text = text.split("\n\n", 1)[0].strip()
        return LanguageGenerationResult(
            text=text,
            backend=self.name,
            confidence=0.70 if text else 0.0,
            metadata={
                "learned_generation": True,
                "architecture": "rwkv-7",
                "max_new_tokens": self.max_new_tokens,
                "context_packet": "beliefs+goals+world+memory",
            },
        )

    def capabilities(self) -> dict:
        return {
            "read": True,
            "embed": True,
            "extract": bool(self.extract_proposals),
            "generate": True,
            "native_passthrough": False,
            "learned_language": True,
            "learned_reader": True,
            "learned_generation": True,
            "attention_free": True,
            "architecture": "rwkv-7",
            "embedding_kind": "recurrent-state-pooling",
            "proposal_extractor": "constrained_json_v1" if self.extract_proposals else "disabled",
        }

    def health(self) -> dict:
        return {
            "backend": self.name,
            "ready": bool(self._ready),
            "load_error": self._load_error,
            "runtime_available": self.runtime_available(),
            "model_path": self.model_path,
            "strategy": self.strategy,
            "tokenizer": self.tokenizer_name,
            "capabilities": self.capabilities(),
        }

    def close(self) -> None:
        self.model = None
        self.pipeline = None
        self._ready = False
