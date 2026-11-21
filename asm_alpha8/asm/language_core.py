from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import hashlib
import math
import time
from typing import Any, Callable, Dict, Iterable, List, Mapping

from .encoder import ConceptEncoder
from .mental_language import MentalLanguagePerception


@dataclass(slots=True)
class LanguageProposal:
    """A language backend's *proposal*, never an authoritative ASM fact."""

    kind: str
    payload: Dict[str, Any]
    confidence: float
    source: str = "language_core"
    evidence: List[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "kind": self.kind,
            "payload": dict(self.payload),
            "confidence": float(self.confidence),
            "source": self.source,
            "evidence": list(self.evidence),
        }


def validate_language_proposal(proposal: LanguageProposal) -> tuple[bool, str | None]:
    """Fail-closed schema validation for untrusted language backends."""
    if not isinstance(proposal, LanguageProposal):
        return False, "proposal_type"
    try:
        confidence = float(proposal.confidence)
    except Exception:
        return False, "confidence_type"
    if not math.isfinite(confidence) or not (0.0 <= confidence <= 1.0):
        return False, "confidence_range"
    if not isinstance(proposal.payload, dict):
        return False, "payload_type"
    if proposal.kind not in {"belief", "nested_belief", "drive", "self_outcome"}:
        return False, "unsupported_kind"

    p = proposal.payload
    def bounded_text(key: str, *, allow_empty: bool = False) -> bool:
        value = p.get(key)
        return isinstance(value, str) and (allow_empty or bool(value.strip())) and len(value) <= 512

    if proposal.kind == "belief":
        if not bounded_text("holder") or not bounded_text("proposition_text"):
            return False, "belief_schema"
        if "polarity" in p and not isinstance(p["polarity"], bool):
            return False, "belief_polarity"
    elif proposal.kind == "nested_belief":
        path = p.get("path")
        if not isinstance(path, (list, tuple)) or not (2 <= len(path) <= 3):
            return False, "nested_path"
        if any(not isinstance(x, str) or not x.strip() or len(x) > 128 for x in path):
            return False, "nested_path_item"
        if not bounded_text("proposition_text"):
            return False, "nested_proposition"
        if "polarity" in p and not isinstance(p["polarity"], bool):
            return False, "nested_polarity"
    elif proposal.kind == "drive":
        if not bounded_text("holder") or not bounded_text("proposition_text"):
            return False, "drive_schema"
        if str(p.get("kind", "")) not in {"goal", "fear", "expectation"}:
            return False, "drive_kind"
        try:
            priority = float(p.get("priority", 0.6))
        except Exception:
            return False, "drive_priority_type"
        if not math.isfinite(priority) or not (0.0 <= priority <= 1.0):
            return False, "drive_priority_range"
    elif proposal.kind == "self_outcome":
        if not bounded_text("strategy"):
            return False, "outcome_strategy"
        if not isinstance(p.get("success"), bool):
            return False, "outcome_success"
        if "task_family" in p and not bounded_text("task_family"):
            return False, "outcome_task_family"
        if "score" in p:
            try:
                score = float(p["score"])
            except Exception:
                return False, "outcome_score_type"
            if not math.isfinite(score) or not (0.0 <= score <= 1.0):
                return False, "outcome_score_range"
    return True, None


@dataclass(slots=True)
class LanguageReadResult:
    text: str
    backend: str
    tokens: List[str]
    embedding: List[float]
    proposals: List[LanguageProposal]
    elapsed_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self, *, include_embedding: bool = True) -> dict:
        out = {
            "backend": self.backend,
            "tokens": list(self.tokens),
            "proposals": [p.as_dict() for p in self.proposals],
            "elapsed_ms": float(self.elapsed_ms),
            "metadata": dict(self.metadata),
        }
        if include_embedding:
            out["embedding"] = list(self.embedding)
        else:
            out["embedding_dims"] = len(self.embedding)
        return out


@dataclass(slots=True)
class LanguageGenerationResult:
    text: str
    backend: str
    confidence: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "text": self.text,
            "backend": self.backend,
            "confidence": float(self.confidence),
            "metadata": dict(self.metadata),
        }


class LanguageCore(ABC):
    """
    Swappable language-cortex contract.

    A backend may be a frozen RWKV/Mamba-like recurrent model, a remote model,
    or the dependency-free fallback.  It may *propose* interpretations, but ASM
    owns acceptance, belief revision, memory and cognition.
    """

    name = "abstract"
    # True means ASM's existing native parsers remain the authority and backend
    # proposals are diagnostic only.  Neural/external backends normally set False.
    native_passthrough = False

    @abstractmethod
    def read(self, text: str) -> LanguageReadResult:
        raise NotImplementedError

    @abstractmethod
    def generate(self, state: Mapping[str, Any], *, instruction: str = "") -> LanguageGenerationResult:
        raise NotImplementedError

    def capabilities(self) -> dict:
        return {
            "read": True,
            "embed": True,
            "extract": True,
            "generate": True,
            "native_passthrough": bool(self.native_passthrough),
        }

    def health(self) -> dict:
        return {"backend": self.name, "ready": True, "capabilities": self.capabilities()}

    def close(self) -> None:
        return None


class FallbackLanguageCore(LanguageCore):
    """
    Dependency-free adapter around ASM's existing language perception.

    The hashed embedding is an interface placeholder, not a semantic embedding
    comparable to a neural language model.  It exists so vector-memory plumbing
    can be built before a recurrent backend is attached.
    """

    name = "fallback"
    native_passthrough = True

    def __init__(self, encoder: ConceptEncoder, *, embedding_dims: int = 96):
        self.encoder = encoder
        self.embedding_dims = max(16, int(embedding_dims))

    def _hashed_embedding(self, text: str) -> List[float]:
        vec = [0.0] * self.embedding_dims
        stems = self.encoder.content_stems(text)
        for stem in stems:
            digest = hashlib.blake2b(stem.encode("utf-8"), digest_size=16).digest()
            idx = int.from_bytes(digest[:8], "little") % self.embedding_dims
            sign = 1.0 if (digest[8] & 1) == 0 else -1.0
            vec[idx] += sign
        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 0:
            vec = [x / norm for x in vec]
        return vec

    def _proposals(self, text: str) -> List[LanguageProposal]:
        rows: List[LanguageProposal] = []

        nested = MentalLanguagePerception.parse_nested(text, max_order=3)
        if nested:
            rows.append(LanguageProposal(
                "nested_belief",
                {
                    "path": nested["path"],
                    "proposition_text": nested["proposition_text"],
                    "polarity": bool(nested.get("polarity", True)),
                },
                float(nested.get("confidence", 0.8)),
                source="fallback:mental_language",
            ))

        belief = MentalLanguagePerception.parse_direct_belief(text)
        if belief:
            rows.append(LanguageProposal(
                "belief",
                {
                    "holder": belief["holder"],
                    "proposition_text": belief["proposition_text"],
                    "polarity": bool(belief.get("polarity", True)),
                },
                float(belief.get("confidence", 0.8)),
                source="fallback:mental_language",
            ))

        drive = MentalLanguagePerception.parse_drive(text)
        if drive:
            rows.append(LanguageProposal(
                "drive",
                {
                    "holder": drive["holder"],
                    "kind": drive["kind"],
                    "proposition_text": drive["proposition_text"],
                    "priority": float(drive.get("priority", 0.6)),
                },
                float(drive.get("confidence", 0.8)),
                source="fallback:mental_language",
            ))

        outcome = MentalLanguagePerception.parse_self_outcome(text)
        if outcome:
            rows.append(LanguageProposal(
                "self_outcome",
                {
                    "task_family": outcome["task_family"],
                    "strategy": outcome["strategy"],
                    "success": bool(outcome["success"]),
                    "score": float(outcome.get("confidence", 0.8)),
                },
                float(outcome.get("confidence", 0.8)),
                source="fallback:mental_language",
            ))

        return rows

    def read(self, text: str) -> LanguageReadResult:
        started = time.perf_counter()
        result = LanguageReadResult(
            text=text,
            backend=self.name,
            tokens=self.encoder.tokenize(text),
            embedding=self._hashed_embedding(text),
            proposals=self._proposals(text),
            metadata={"embedding_kind": "hashed-placeholder"},
        )
        result.elapsed_ms = (time.perf_counter() - started) * 1000.0
        return result

    def generate(self, state: Mapping[str, Any], *, instruction: str = "") -> LanguageGenerationResult:
        # This intentionally remains conservative. v0.2.0-alpha.1 defines the
        # writer contract; a later recurrent backend will provide learned fluency.
        focus = None
        attention = state.get("attention") if isinstance(state, Mapping) else None
        if isinstance(attention, Mapping):
            focus = attention.get("epicenter")
        internal = state.get("internal", {}) if isinstance(state, Mapping) else {}
        parts = []
        if instruction:
            parts.append(str(instruction).strip())
        if focus:
            parts.append(f"Current focus: {focus}.")
        if isinstance(internal, Mapping) and internal:
            confidence = float(internal.get("confidence", 0.5))
            parts.append(f"Internal confidence: {confidence:.2f}.")
        text = " ".join(parts) or "ASM language cortex fallback is active."
        return LanguageGenerationResult(
            text=text,
            backend=self.name,
            confidence=0.35,
            metadata={"learned_generation": False},
        )

    def capabilities(self) -> dict:
        out = super().capabilities()
        out.update({
            "learned_language": False,
            "learned_generation": False,
            "embedding_kind": "hashed-placeholder",
        })
        return out


class CallableLanguageCore(LanguageCore):
    """Small adapter for experiments/tests and future local recurrent runtimes."""

    name = "callable"
    native_passthrough = False

    def __init__(
        self,
        reader: Callable[[str], LanguageReadResult],
        writer: Callable[[Mapping[str, Any], str], LanguageGenerationResult],
        *,
        name: str = "callable",
        capabilities: Mapping[str, Any] | None = None,
    ):
        self._reader = reader
        self._writer = writer
        self.name = str(name)
        self._capabilities = dict(capabilities or {})

    def read(self, text: str) -> LanguageReadResult:
        result = self._reader(text)
        if not isinstance(result, LanguageReadResult):
            raise TypeError("language reader must return LanguageReadResult")
        return result

    def generate(self, state: Mapping[str, Any], *, instruction: str = "") -> LanguageGenerationResult:
        result = self._writer(state, instruction)
        if not isinstance(result, LanguageGenerationResult):
            raise TypeError("language writer must return LanguageGenerationResult")
        return result

    def capabilities(self) -> dict:
        out = super().capabilities()
        out.update(self._capabilities)
        return out


_BACKENDS: Dict[str, Callable[[Any, ConceptEncoder], LanguageCore]] = {}


def register_language_core(name: str, factory: Callable[[Any, ConceptEncoder], LanguageCore]) -> None:
    key = str(name).strip().lower()
    if not key:
        raise ValueError("language-core backend name cannot be empty")
    _BACKENDS[key] = factory


def available_language_cores() -> List[str]:
    return sorted(_BACKENDS)


def create_language_core(name: str, config: Any, encoder: ConceptEncoder) -> LanguageCore:
    key = str(name or "fallback").strip().lower()
    factory = _BACKENDS.get(key)
    if factory is None:
        raise ValueError(
            f"unknown language-core backend {name!r}; available={available_language_cores()}"
        )
    core = factory(config, encoder)
    if not isinstance(core, LanguageCore):
        raise TypeError("language-core factory must return LanguageCore")
    return core


register_language_core(
    "fallback",
    lambda config, encoder: FallbackLanguageCore(
        encoder,
        embedding_dims=getattr(config, "language_core_embedding_dims", 96),
    ),
)



def _create_recurrent_core(config: Any, encoder: ConceptEncoder) -> LanguageCore:
    from pathlib import Path
    from .recurrent_reader import FrozenRecurrentLanguageCore
    data_dir = Path(__file__).resolve().parent / "data"
    return FrozenRecurrentLanguageCore(
        encoder,
        model_path=data_dir / "recurrent_reader_v020a2.pt",
        metadata_path=data_dir / "recurrent_reader_v020a2.json",
        min_intent_confidence=getattr(config, "language_core_recurrent_min_intent_confidence", 0.80),
        min_validation_accuracy=getattr(config, "language_core_recurrent_min_validation_accuracy", 0.80),
    )


def _create_rwkv7_core(config: Any, encoder: ConceptEncoder) -> LanguageCore:
    from .rwkv7_core import RWKV7LanguageCore
    return RWKV7LanguageCore(
        encoder,
        model_path=getattr(config, "rwkv7_model_path", ""),
        strategy=getattr(config, "rwkv7_strategy", "cpu fp32"),
        tokenizer=getattr(config, "rwkv7_tokenizer", "rwkv_vocab_v20230424"),
        embedding_dims=getattr(config, "rwkv7_embedding_dims", 128),
        chunk_len=getattr(config, "rwkv7_chunk_len", 128),
        max_new_tokens=getattr(config, "rwkv7_max_new_tokens", 96),
        temperature=getattr(config, "rwkv7_temperature", 0.8),
        top_p=getattr(config, "rwkv7_top_p", 0.5),
        extract_proposals=getattr(config, "rwkv7_extract_proposals", True),
        extractor_max_tokens=getattr(config, "rwkv7_extractor_max_tokens", 160),
    )


register_language_core("recurrent", _create_recurrent_core)
register_language_core("rwkv7", _create_rwkv7_core)
