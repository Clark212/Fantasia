"""Small trained GRU surface realizer with opaque, exact-copy cognitive slots.

This is a learned token decoder, not an output-template classifier. It cannot
learn/store user facts: model input contains slot *presence*, never slot content.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import time

from .cognitive_packet import CognitivePacket, hybrid_generate

ACTIONS = ("greeting", "wellbeing", "identity", "gratitude", "farewell",
           "negative_affect", "positive_affect", "uncertainty", "confusion",
           "stored", "listening", "belief_report", "memory_report",
           "previous_message", "cognitive_report")
SLOTS = ("claim", "confidence", "curiosity")
TOKEN = re.compile(r"<[^>]+>|[A-Za-z]+(?:[-'][A-Za-z]+)*|[0-9]+|[^\w\s]", re.UNICODE)


def tokenize(text):
    return TOKEN.findall(text)


def detokenize(tokens):
    text = " ".join(tokens)
    return re.sub(r"\s+([.,!?;:])", r"\1", text)


def condition(packet):
    return ([float(packet.user_intent == a) for a in ACTIONS]
            + [float(s in packet.slots) for s in SLOTS]
            + [max(0., min(1., packet.uncertainty)), float(packet.style == "brief")])


def make_model(vocab_size, embedding_dim=40, hidden_dim=80):
    from torch import nn

    class WriterGRU(nn.Module):
        def __init__(self):
            super().__init__()
            self.embedding = nn.Embedding(vocab_size, embedding_dim, padding_idx=0)
            self.condition = nn.Linear(len(ACTIONS) + len(SLOTS) + 2, hidden_dim)
            self.gru = nn.GRU(embedding_dim, hidden_dim, batch_first=True)
            self.output = nn.Linear(hidden_dim, vocab_size)

        def forward(self, ids, features, hidden=None):
            if hidden is None:
                hidden = self.condition(features).tanh().unsqueeze(0)
            out, hidden = self.gru(self.embedding(ids), hidden)
            return self.output(out), hidden

    return WriterGRU()


class RecurrentWriter:
    def __init__(self, model_path=None, *, max_tokens=80, min_confidence=.65):
        self.path = Path(model_path) if model_path else Path(__file__).parent / "data" / "recurrent_writer_v020a5.pt"
        self.max_tokens = max(1, min(256, int(max_tokens)))
        self.min_confidence = float(min_confidence)
        self.model = None
        self.error = None
        self.meta = {}
        try:
            import torch
            meta = json.loads(self.path.with_suffix(".json").read_text())
            if hashlib.sha256(self.path.read_bytes()).hexdigest() != meta["sha256"]:
                raise ValueError("writer checkpoint checksum mismatch")
            self.vocab = meta["vocab"]
            self.ids = {w: i for i, w in enumerate(self.vocab)}
            model = make_model(len(self.vocab), meta["embedding_dim"], meta["hidden_dim"])
            model.load_state_dict(torch.load(self.path, map_location="cpu", weights_only=True))
            model.eval().requires_grad_(False)
            self.model, self.meta = model, meta
        except Exception as exc:
            self.error = f"{type(exc).__name__}: {exc}"

    def health(self):
        return {"backend": "recurrent-writer", "ready": self.model is not None,
                "load_error": self.error, "attention_free": True, "architecture": "conditioned-GRU-decoder",
                "weights_frozen": self.model is not None,
                "parameters": self.meta.get("parameters", 0), "checkpoint_bytes": self.meta.get("checkpoint_bytes", 0)}

    def draft(self, packet):
        if self.model is None:
            raise RuntimeError(self.error or "writer unavailable")
        if packet.user_intent not in ACTIONS:
            raise ValueError("unsupported cognitive speech act")
        import torch
        features = torch.tensor([condition(packet)], dtype=torch.float32)
        x = torch.tensor([[self.ids["<bos>"]]])
        hidden, words, confidence = None, [], []
        with torch.inference_mode():
            for _ in range(self.max_tokens):
                logits, hidden = self.model(x, features, hidden)
                probs = logits[0, -1].softmax(-1)
                idx = int(probs.argmax())
                word = self.vocab[idx]
                confidence.append(float(probs[idx]))
                if word == "<eos>":
                    return words, min(confidence)
                if word in {"<pad>", "<bos>"}:
                    raise ValueError("invalid decoder control token")
                words.append(word)
                x = torch.tensor([[idx]])
        raise ValueError("writer token limit reached")

    def generate(self, packet: CognitivePacket) -> dict:
        started = time.perf_counter()
        try:
            words, confidence = self.draft(packet)
            used = [w[1:-1] for w in words if w.startswith("<")]
            if sorted(used) != sorted(packet.slots):
                raise ValueError("missing, duplicated or unsupported slot")
            if confidence < self.min_confidence:
                raise ValueError("writer confidence below gate")
            # Slots are substituted only once, AFTER decoding. User text cannot
            # enter the decoder, create new slots, or recursively expand itself.
            surface = detokenize(words)
            text = re.sub(r"<([^>]+)>", lambda m: packet.slots[m.group(1)], surface)
            if not text.strip():
                raise ValueError("empty output")
            return {"text": text, "backend": "recurrent-writer", "learned_generation": True,
                    "fallback": False, "confidence": confidence, "surface": surface,
                    "slots_used": used, "elapsed_ms": (time.perf_counter() - started) * 1000}
        except Exception as exc:
            return {"text": hybrid_generate(packet), "backend": "hybrid-fallback",
                    "learned_generation": False, "fallback": True, "confidence": 0.,
                    "fallback_reason": f"{type(exc).__name__}: {exc}",
                    "elapsed_ms": (time.perf_counter() - started) * 1000}
