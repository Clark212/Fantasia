from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
import time
from typing import Any, Dict, List, Mapping

from .encoder import ConceptEncoder
from .language_core import (
    FallbackLanguageCore,
    LanguageCore,
    LanguageGenerationResult,
    LanguageProposal,
    LanguageReadResult,
)


LABELS = (
    "other",
    "belief",
    "nested_belief",
    "drive",
    "self_outcome",
)

@dataclass(slots=True)
class RecurrentReaderPrediction:
    label: str
    confidence: float
    probabilities: Dict[str, float]


class _CharGRUModel:
    """Thin holder so torch is imported only when the recurrent backend is used."""

    def __init__(self, vocab_size: int, embedding_dim: int, hidden_dim: int, num_labels: int, *, bidirectional: bool = True):
        import torch
        from torch import nn

        class Model(nn.Module):
            def __init__(self):
                super().__init__()
                self.embedding = nn.Embedding(vocab_size, embedding_dim, padding_idx=0)
                self.gru = nn.GRU(embedding_dim, hidden_dim, batch_first=True, bidirectional=bidirectional)
                out_dim = hidden_dim * (2 if bidirectional else 1)
                self.norm = nn.LayerNorm(out_dim)
                self.classifier = nn.Linear(out_dim, num_labels)

            def forward(self, ids, lengths=None):
                if lengths is None:
                    lengths = (ids != 0).sum(dim=1).clamp(min=1)
                emb = self.embedding(ids)
                packed = nn.utils.rnn.pack_padded_sequence(
                    emb,
                    lengths.detach().cpu(),
                    batch_first=True,
                    enforce_sorted=False,
                )
                _out, hidden = self.gru(packed)
                if bidirectional:
                    h = torch.cat([hidden[-2], hidden[-1]], dim=-1)
                else:
                    h = hidden[-1]
                h = self.norm(h)
                logits = self.classifier(h)
                return logits, h

        self.torch = torch
        self.model = Model()


class FrozenRecurrentLanguageCore(LanguageCore):
    """
    Frozen attention-free character-GRU reader for ASM alpha.2.

    The neural model performs intent-family recognition and provides a learned
    fixed-size embedding. Structured slots are deliberately still recovered by
    ASM's proven deterministic language layer in this stage. This avoids
    pretending alpha.2 has solved arbitrary structured extraction; that belongs
    to a later stage.
    """

    name = "recurrent-reader"
    native_passthrough = False

    def __init__(
        self,
        encoder: ConceptEncoder,
        *,
        model_path: str | Path,
        metadata_path: str | Path,
        min_intent_confidence: float = 0.60,
        min_validation_accuracy: float = 0.80,
    ):
        self.encoder = encoder
        self.model_path = Path(model_path)
        self.metadata_path = Path(metadata_path)
        self.min_intent_confidence = float(min_intent_confidence)
        self.min_validation_accuracy = float(min_validation_accuracy)
        self.fallback = FallbackLanguageCore(encoder)
        self._loaded = False
        self._load_error: str | None = None
        self._model = None
        self._torch = None
        self._meta: Dict[str, Any] = {}
        self._char_to_id: Dict[str, int] = {}
        self._labels: List[str] = list(LABELS)
        self._max_chars = 192
        self._load()

    def _load(self) -> None:
        try:
            if not self.metadata_path.exists():
                raise FileNotFoundError(self.metadata_path)
            if not self.model_path.exists():
                raise FileNotFoundError(self.model_path)

            meta = json.loads(self.metadata_path.read_text(encoding="utf-8"))
            labels = list(meta.get("labels", LABELS))
            validation_accuracy = float(meta.get("validation_accuracy", 0.0))
            if validation_accuracy < self.min_validation_accuracy:
                raise RuntimeError(
                    f"recurrent reader validation accuracy {validation_accuracy:.4f} "
                    f"is below required {self.min_validation_accuracy:.4f}"
                )
            chars = list(meta["chars"])
            char_to_id = {str(ch): i + 1 for i, ch in enumerate(chars)}
            holder = _CharGRUModel(
                vocab_size=len(chars) + 1,
                embedding_dim=int(meta["embedding_dim"]),
                hidden_dim=int(meta["hidden_dim"]),
                num_labels=len(labels),
                bidirectional=bool(meta.get("bidirectional", True)),
            )
            torch = holder.torch
            state = torch.load(self.model_path, map_location="cpu", weights_only=True)
            holder.model.load_state_dict(state)
            holder.model.eval()
            for param in holder.model.parameters():
                param.requires_grad_(False)

            self._model = holder.model
            self._torch = torch
            self._meta = meta
            self._labels = labels
            self._char_to_id = char_to_id
            self._max_chars = int(meta.get("max_chars", 192))
            self._loaded = True
            self._load_error = None
        except Exception as exc:
            self._loaded = False
            self._load_error = f"{type(exc).__name__}: {exc}"

    def _encode_chars(self, text: str):
        torch = self._torch
        assert torch is not None
        normalized = " ".join(text.lower().replace("’", "'").split())[: self._max_chars]
        ids = [self._char_to_id.get(ch, 0) for ch in normalized]
        if not ids:
            ids = [0]
        return torch.tensor([ids], dtype=torch.long)

    def _predict(self, text: str) -> tuple[RecurrentReaderPrediction, List[float]]:
        if not self._loaded or self._model is None or self._torch is None:
            raise RuntimeError(self._load_error or "recurrent reader not loaded")
        torch = self._torch
        ids = self._encode_chars(text)
        with torch.inference_mode():
            logits, hidden = self._model(ids)
            probs = torch.softmax(logits[0], dim=-1)
            idx = int(torch.argmax(probs).item())
            confidence = float(probs[idx].item())
            vector = hidden[0].detach().to(dtype=torch.float32).cpu().tolist()
        norm = math.sqrt(sum(float(x) * float(x) for x in vector))
        if norm > 0:
            vector = [float(x) / norm for x in vector]
        probability_map = {
            label: float(probs[i].item())
            for i, label in enumerate(self._labels)
        }
        return (
            RecurrentReaderPrediction(
                label=self._labels[idx],
                confidence=confidence,
                probabilities=probability_map,
            ),
            vector,
        )

    @staticmethod
    def _proposal_matches(label: str, proposal: LanguageProposal) -> bool:
        if label == "belief":
            return proposal.kind == "belief"
        if label == "nested_belief":
            return proposal.kind == "nested_belief"
        if label == "drive":
            return proposal.kind == "drive"
        if label == "self_outcome":
            return proposal.kind == "self_outcome"
        return False

    def read(self, text: str) -> LanguageReadResult:
        started = time.perf_counter()
        prediction, embedding = self._predict(text)

        # The neural reader decides the semantic intent family. Alpha.2 still
        # delegates slot recovery to the stable native layer, then only releases
        # matching proposals. That gives the neural model real control without
        # letting it invent malformed persistent state.
        deterministic = self.fallback.read(text)
        proposals: List[LanguageProposal] = []
        if prediction.confidence >= self.min_intent_confidence:
            for proposal in deterministic.proposals:
                if self._proposal_matches(prediction.label, proposal):
                    fused_conf = min(
                        0.99,
                        0.58 * prediction.confidence + 0.42 * float(proposal.confidence),
                    )
                    proposals.append(LanguageProposal(
                        kind=proposal.kind,
                        payload=dict(proposal.payload),
                        confidence=fused_conf,
                        source="recurrent-reader",
                        evidence=[
                            f"intent={prediction.label}",
                            f"neural_confidence={prediction.confidence:.4f}",
                            "slots=native-safe-slotter",
                        ],
                    ))

        result = LanguageReadResult(
            text=text,
            backend=self.name,
            tokens=self.encoder.tokenize(text),
            embedding=embedding,
            proposals=proposals,
            metadata={
                "learned_reader": True,
                "attention_free": True,
                "architecture": "char-bi-gru",
                "intent": prediction.label,
                "intent_confidence": prediction.confidence,
                "intent_probabilities": prediction.probabilities,
                "slots": "native-safe-slotter",
                "weights_frozen": True,
                "model_validation_accuracy": float(self._meta.get("validation_accuracy", 0.0)),
            },
        )
        result.elapsed_ms = (time.perf_counter() - started) * 1000.0
        return result

    def generate(self, state: Mapping[str, Any], *, instruction: str = "") -> LanguageGenerationResult:
        # Alpha.2 is intentionally the reader stage. Keep generation honest and
        # route it through the stable fallback until the writer stage.
        out = self.fallback.generate(state, instruction=instruction)
        out.backend = self.name
        out.metadata.update({
            "learned_generation": False,
            "generation_stage": "deferred",
            "reader_is_learned": True,
        })
        return out

    def capabilities(self) -> dict:
        return {
            "read": True,
            "embed": True,
            "extract": True,
            "generate": True,
            "native_passthrough": False,
            "learned_language": True,
            "learned_reader": True,
            "learned_generation": False,
            "attention_free": True,
            "architecture": "char-bi-gru",
            "embedding_kind": "frozen-recurrent-hidden-state",
            "embedding_dims": int(self._meta.get("hidden_dim", 0)) * (2 if self._meta.get("bidirectional", False) else 1),
            "slots": "native-safe-slotter",
        }

    def health(self) -> dict:
        return {
            "backend": self.name,
            "ready": bool(self._loaded),
            "load_error": self._load_error,
            "model_path": str(self.model_path),
            "metadata_path": str(self.metadata_path),
            "weights_frozen": bool(self._loaded),
            "validation_accuracy": float(self._meta.get("validation_accuracy", 0.0)),
            "capabilities": self.capabilities(),
        }
