from __future__ import annotations

import json
from pathlib import Path
from typing import Sequence


class FrozenSocialProbe:
    """High-threshold probe over the frozen recurrent reader hidden state."""

    def __init__(
        self,
        *,
        model_path: str | Path,
        metadata_path: str | Path,
        threshold: float = 0.99,
        min_validation_accuracy: float = 0.80,
    ):
        self.model_path=Path(model_path)
        self.metadata_path=Path(metadata_path)
        self.threshold=float(threshold)
        self.min_validation_accuracy=float(min_validation_accuracy)
        self._model=None
        self._torch=None
        self._meta={}
        self._ready=False
        self._error=None
        self._load()

    def _load(self):
        try:
            import torch
            from torch import nn
            meta=json.loads(self.metadata_path.read_text(encoding="utf-8"))
            if float(meta.get("overall_accuracy",0.0)) < self.min_validation_accuracy:
                raise RuntimeError("social probe validation floor not met")
            dims=int(meta["input_dims"])
            hidden=int(meta["hidden_dims"])
            model=nn.Sequential(nn.Linear(dims,hidden),nn.Tanh(),nn.Linear(hidden,2))
            model.load_state_dict(torch.load(self.model_path,map_location="cpu",weights_only=True))
            model.eval()
            for p in model.parameters():
                p.requires_grad_(False)
            self._model=model; self._torch=torch; self._meta=meta; self._ready=True
        except Exception as exc:
            self._ready=False
            self._error=f"{type(exc).__name__}: {exc}"

    def probability(self, embedding: Sequence[float], *, backend: str) -> float:
        if not self._ready or backend != "recurrent-reader":
            return 0.0
        if len(embedding) != int(self._meta.get("input_dims",0)):
            return 0.0
        torch=self._torch
        with torch.inference_mode():
            x=torch.tensor([list(embedding)],dtype=torch.float32)
            p=torch.softmax(self._model(x),dim=-1)[0,1]
        return float(p.item())

    def health(self) -> dict:
        return {
            "ready":self._ready,
            "load_error":self._error,
            "threshold":self.threshold,
            "validation_accuracy":float(self._meta.get("overall_accuracy",0.0)),
            "architecture":"probe-on-recurrent-state",
        }
