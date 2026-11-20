"""DEV16 learning engine: models that actually learn from data, with honest evaluation.

Before DEV16, `asm.learning` stored and ranked experience records but contained no learner: nothing was fitted,
updated or used to predict. This module adds trainable models, standard library only (no numpy, torch or
transformers), deterministic for a given seed and input order.

Components
- FeatureHasher        sparse features from {name: value} dicts (numeric, categorical, boolean); hashing trick, so the
                        feature space need not be known in advance.
- LogisticModel        online logistic regression, AdaGrad + L2, binary; `partial_fit` learns incrementally.
- CountModel           naive Bayes over categorical features with Laplace smoothing: small-data baseline, readable.
- IsotonicCalibrator   maps scores to calibrated probabilities (pool-adjacent-violators), fitted on HELD-OUT data.
- group_split          train/test split in which no group (e.g. a project) appears on both sides: the leakage that makes
                        learned-model numbers look better than they are.
- evaluate_binary      log loss, Brier, accuracy, AUC, each beside the base-rate baseline.
- evaluate_ranking     top-1/top-5/MRR of the true item within groups, beside the given (unlearned) order.
- LearnedModel         model + calibrator + training provenance (data hashes, counts per source and evidence status,
                        seed) sealed with SHA-256; `load` refuses a model whose seal does not verify.
- examples_from_experiences  only VERIFIED evidence trains a model: records with evidence_status "generated" are refused
                        unless their metadata says they were verified by execution (the DEV16 data rule).

What this does not claim: a fitted model is evidence about the data it was evaluated on, not a capability. Every
use in ASM must report held-out metrics against the unlearned baseline, as `evaluate_*` returns them.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

HASH_BITS = 18


def _h(text: str, bits: int) -> int:
    return int.from_bytes(hashlib.blake2b(text.encode("utf-8"), digest_size=8).digest(), "big") & ((1 << bits) - 1)


class FeatureHasher:
    """{name: value} -> {index: value}. Numbers keep their value under their name; strings and booleans become
    indicator features `name=value`. A constant bias feature is always present."""

    def __init__(self, bits: int = HASH_BITS):
        if not 8 <= bits <= 24:
            raise ValueError("bits must be between 8 and 24")
        self.bits = bits

    def transform(self, features: Mapping[str, Any]) -> dict:
        out: dict = {_h("__bias__", self.bits): 1.0}
        for name, value in features.items():
            if value is None:
                continue
            if isinstance(value, bool):
                key, v = f"{name}={value}", 1.0
            elif isinstance(value, (int, float)):
                v = float(value)
                if not math.isfinite(v):
                    raise ValueError(f"feature {name!r} is not finite")
                key = name
            elif isinstance(value, str):
                key, v = f"{name}={value}", 1.0
            elif isinstance(value, (list, tuple, set, frozenset)):  # bag of categorical values
                for item in sorted(map(str, value)):
                    i = _h(f"{name}={item}", self.bits)
                    out[i] = out.get(i, 0.0) + 1.0
                continue
            else:
                raise TypeError(f"feature {name!r} has unsupported type {type(value).__name__}")
            i = _h(key, self.bits)
            out[i] = out.get(i, 0.0) + v
        return out


def _sigmoid(z: float) -> float:
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    e = math.exp(z)
    return e / (1.0 + e)


class LogisticModel:
    """Binary logistic regression trained by AdaGrad with L2 (sparse weights, so millions of possible features cost
    only what is used). Optional class weighting for rare positives (e.g. one true fix among 80 candidates)."""
    kind = "logistic"

    def __init__(self, bits: int = HASH_BITS, lr: float = 0.3, l2: float = 1e-4, epochs: int = 8, seed: int = 0,
                 balance: bool = True):
        self.hasher = FeatureHasher(bits)
        self.lr, self.l2, self.epochs, self.seed, self.balance = lr, l2, epochs, seed, balance
        self.w: dict = {}
        self.g2: dict = {}
        self.seen = 0
        self.pos_weight = 1.0

    def _score(self, x: dict) -> float:
        return sum(self.w.get(i, 0.0) * v for i, v in x.items())

    def decision(self, features: Mapping[str, Any]) -> float:
        return self._score(self.hasher.transform(features))

    def predict_proba(self, features: Mapping[str, Any]) -> float:
        return _sigmoid(self.decision(features))

    def partial_fit(self, rows: Sequence[Mapping[str, Any]], labels: Sequence[int]) -> "LogisticModel":
        """One pass over (rows, labels) in the given order: incremental learning from new experience."""
        for feats, y in zip(rows, labels):
            self._step(self.hasher.transform(feats), int(y))
        return self

    def _step(self, x: dict, y: int) -> None:
        if y not in (0, 1):
            raise ValueError("labels must be 0 or 1")
        p = _sigmoid(self._score(x))
        weight = self.pos_weight if y == 1 else 1.0
        err = (p - y) * weight
        for i, v in x.items():
            g = err * v + self.l2 * self.w.get(i, 0.0)
            acc = self.g2.get(i, 0.0) + g * g
            self.g2[i] = acc
            self.w[i] = self.w.get(i, 0.0) - self.lr * g / math.sqrt(acc + 1e-12)
        self.seen += 1

    def fit(self, rows: Sequence[Mapping[str, Any]], labels: Sequence[int]) -> "LogisticModel":
        if len(rows) != len(labels) or not rows:
            raise ValueError("rows and labels must be non-empty and of equal length")
        pos = sum(1 for y in labels if y == 1)
        if self.balance and 0 < pos < len(labels):
            self.pos_weight = (len(labels) - pos) / pos
        xs = [self.hasher.transform(r) for r in rows]
        order = list(range(len(xs)))
        rng = random.Random(self.seed)
        for _ in range(self.epochs):
            rng.shuffle(order)
            for k in order:
                self._step(xs[k], int(labels[k]))
        return self

    def to_dict(self) -> dict:
        return {"kind": self.kind, "bits": self.hasher.bits, "lr": self.lr, "l2": self.l2, "epochs": self.epochs,
                "seed": self.seed, "balance": self.balance, "pos_weight": self.pos_weight, "seen": self.seen,
                "w": {str(k): v for k, v in sorted(self.w.items()) if v != 0.0}}  # full precision: reload is exact

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "LogisticModel":
        m = cls(d["bits"], d["lr"], d["l2"], d["epochs"], d["seed"], d["balance"])
        m.w = {int(k): float(v) for k, v in d["w"].items()}
        m.pos_weight, m.seen = d["pos_weight"], d["seen"]
        return m


class CountModel:
    """Naive Bayes over categorical features (Laplace alpha). Numeric features are ignored unless pre-binned into
    strings. Readable: `top_evidence` lists the feature values that most raise P(positive)."""
    kind = "counts"

    def __init__(self, alpha: float = 1.0):
        self.alpha = alpha
        self.n = [0, 0]
        self.c: list = [{}, {}]  # per class: "name=value" -> count
        self.names: dict = {}  # feature name -> set of values seen

    @staticmethod
    def _items(features: Mapping[str, Any]) -> list:
        out = []
        for k, v in features.items():
            if isinstance(v, bool) or isinstance(v, str):
                out.append((k, str(v)))
            elif isinstance(v, (list, tuple, set, frozenset)):
                out += [(k, str(x)) for x in v]
        return out

    def partial_fit(self, rows, labels) -> "CountModel":
        for feats, y in zip(rows, labels):
            y = int(y)
            self.n[y] += 1
            for k, v in self._items(feats):
                key = f"{k}={v}"
                self.c[y][key] = self.c[y].get(key, 0) + 1
                self.names.setdefault(k, set()).add(v)
        return self

    fit = partial_fit

    def decision(self, features: Mapping[str, Any]) -> float:
        total = self.n[0] + self.n[1]
        if total == 0:
            return 0.0
        s = math.log((self.n[1] + self.alpha) / (self.n[0] + self.alpha))
        for k, v in self._items(features):
            card = len(self.names.get(k, ())) + 1
            key = f"{k}={v}"
            p1 = (self.c[1].get(key, 0) + self.alpha) / (self.n[1] + self.alpha * card)
            p0 = (self.c[0].get(key, 0) + self.alpha) / (self.n[0] + self.alpha * card)
            s += math.log(p1 / p0)
        return s

    def predict_proba(self, features) -> float:
        return _sigmoid(self.decision(features))

    def top_evidence(self, k: int = 10) -> list:
        rows = []
        for key in set(self.c[0]) | set(self.c[1]):
            name = key.split("=", 1)[0]
            card = len(self.names.get(name, ())) + 1
            p1 = (self.c[1].get(key, 0) + self.alpha) / (self.n[1] + self.alpha * card)
            p0 = (self.c[0].get(key, 0) + self.alpha) / (self.n[0] + self.alpha * card)
            rows.append((round(math.log(p1 / p0), 4), key, self.c[1].get(key, 0), self.c[0].get(key, 0)))
        return sorted(rows, reverse=True)[:k]

    def to_dict(self) -> dict:
        return {"kind": self.kind, "alpha": self.alpha, "n": self.n, "c": [dict(sorted(x.items())) for x in self.c],
                "names": {k: sorted(v) for k, v in sorted(self.names.items())}}

    @classmethod
    def from_dict(cls, d) -> "CountModel":
        m = cls(d["alpha"])
        m.n, m.c = list(d["n"]), [dict(x) for x in d["c"]]
        m.names = {k: set(v) for k, v in d["names"].items()}
        return m


class IsotonicCalibrator:
    """Monotone map score -> probability (pool-adjacent-violators). Fit it on data the model was NOT trained on."""

    def __init__(self):
        self.x: list = []
        self.y: list = []

    def fit(self, scores: Sequence[float], labels: Sequence[int]) -> "IsotonicCalibrator":
        pts = sorted(zip(scores, labels))
        blocks = []  # [sum_y, n, max_x]
        for s, y in pts:
            blocks.append([float(y), 1, s])
            while len(blocks) > 1 and blocks[-2][0] / blocks[-2][1] >= blocks[-1][0] / blocks[-1][1]:
                y2, n2, x2 = blocks.pop()
                blocks[-1][0] += y2
                blocks[-1][1] += n2
                blocks[-1][2] = x2
        self.x = [b[2] for b in blocks]
        # Laplace-smoothed block means: a block of 3 negatives must not become probability 0 (log loss would explode
        # on the first positive that lands there); found by the engine's own synthetic check
        self.y = [(b[0] + 1.0) / (b[1] + 2.0) for b in blocks]
        for i in range(1, len(self.y)):  # smoothing can break monotonicity slightly; restore it
            self.y[i] = max(self.y[i], self.y[i - 1])
        return self

    def __call__(self, score: float) -> float:
        if not self.x:
            raise ValueError("calibrator not fitted")
        for x, y in zip(self.x, self.y):
            if score <= x:
                return y
        return self.y[-1]

    def to_dict(self) -> dict:
        return {"x": self.x, "y": self.y}

    @classmethod
    def from_dict(cls, d) -> "IsotonicCalibrator":
        c = cls()
        c.x, c.y = list(d["x"]), list(d["y"])
        return c


# ----------------------------------------------------------------------------- splits and metrics
def group_split(groups: Sequence[str], test_fraction: float = 0.3, seed: int = 0) -> tuple:
    """Indices (train, test) such that every group lies entirely on one side. Groups are ordered by a seeded hash,
    so the split is stable when new groups are added."""
    if not 0 < test_fraction < 1:
        raise ValueError("test_fraction must be in (0, 1)")
    uniq = sorted(set(groups), key=lambda g: hashlib.sha256(f"{seed}:{g}".encode()).hexdigest())
    n_test = max(1, round(len(uniq) * test_fraction)) if len(uniq) > 1 else 0
    test_groups = set(uniq[:n_test])
    train = [i for i, g in enumerate(groups) if g not in test_groups]
    test = [i for i, g in enumerate(groups) if g in test_groups]
    return train, test


def _auc(labels, scores) -> float | None:
    pos = [s for s, y in zip(scores, labels) if y == 1]
    neg = [s for s, y in zip(scores, labels) if y == 0]
    if not pos or not neg:
        return None
    ranked = sorted([(s, 1) for s in pos] + [(s, 0) for s in neg])
    rank_sum, i = 0.0, 0
    while i < len(ranked):  # average ranks for ties
        j = i
        while j < len(ranked) and ranked[j][0] == ranked[i][0]:
            j += 1
        avg = (i + 1 + j) / 2
        rank_sum += avg * sum(1 for k in range(i, j) if ranked[k][1] == 1)
        i = j
    return (rank_sum - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))


def evaluate_binary(labels: Sequence[int], probs: Sequence[float], train_base_rate: float | None = None) -> dict:
    """Metrics for probabilities, each beside the base-rate baseline (predict the training positive rate for all)."""
    if not labels or len(labels) != len(probs):
        raise ValueError("need equal-length, non-empty labels and probabilities")
    eps = 1e-12
    base = train_base_rate if train_base_rate is not None else sum(labels) / len(labels)

    def ll(ps):
        return -sum(math.log(max(eps, p if y else 1 - p)) for p, y in zip(ps, labels)) / len(labels)

    def brier(ps):
        return sum((p - y) ** 2 for p, y in zip(ps, labels)) / len(labels)
    flat = [base] * len(labels)
    return {"n": len(labels), "positives": sum(labels), "log_loss": round(ll(probs), 5),
            "log_loss_baseline": round(ll(flat), 5), "brier": round(brier(probs), 5),
            "brier_baseline": round(brier(flat), 5),
            "accuracy": round(sum((p >= 0.5) == bool(y) for p, y in zip(probs, labels)) / len(labels), 4),
            "auc": None if _auc(labels, probs) is None else round(_auc(labels, probs), 4)}


def evaluate_ranking(groups: Sequence[Sequence[tuple]]) -> dict:
    """groups: per task, [(score, is_true, original_position), ...]. Compares the learned order (score, descending;
    ties keep the original order) with the original order. Tasks without a true item are counted, not scored."""
    learned, given, missing = [], [], 0
    for g in groups:
        if not any(t for _, t, _ in g):
            missing += 1
            continue
        by_score = sorted(g, key=lambda r: (-r[0], r[2]))
        by_given = sorted(g, key=lambda r: r[2])
        learned.append(next(i for i, r in enumerate(by_score, 1) if r[1]))
        given.append(next(i for i, r in enumerate(by_given, 1) if r[1]))

    def summary(ranks):
        if not ranks:
            return {"tasks": 0}
        return {"tasks": len(ranks), "top1": sum(r == 1 for r in ranks), "top5": sum(r <= 5 for r in ranks),
                "top20": sum(r <= 20 for r in ranks), "mrr": round(sum(1 / r for r in ranks) / len(ranks), 4),
                "mean_rank": round(sum(ranks) / len(ranks), 2)}
    return {"learned": summary(learned), "given_order": summary(given), "tasks_without_true_item": missing,
            "improved": sum(a < b for a, b in zip(learned, given)), "worsened": sum(a > b for a, b in zip(learned, given))}


# ----------------------------------------------------------------------------- sealed, provenance-carrying models
def _canon(d) -> str:
    return json.dumps(d, sort_keys=True, separators=(",", ":"), allow_nan=False)


@dataclass
class LearnedModel:
    name: str
    model: Any
    calibrator: IsotonicCalibrator | None = None
    provenance: dict = field(default_factory=dict)
    metrics: dict = field(default_factory=dict)

    def proba(self, features: Mapping[str, Any]) -> float:
        s = self.model.decision(features)
        return self.calibrator(s) if self.calibrator is not None else _sigmoid(s)

    def score(self, features: Mapping[str, Any]) -> float:
        return self.model.decision(features)

    def body(self) -> dict:
        return {"name": self.name, "model": self.model.to_dict(),
                "calibrator": self.calibrator.to_dict() if self.calibrator else None,
                "provenance": self.provenance, "metrics": self.metrics}

    def save(self, path) -> str:
        body = self.body()
        seal = hashlib.sha256(_canon(body).encode()).hexdigest()
        with open(path, "w", encoding="utf-8") as f:
            f.write(_canon({"body": body, "sha256": seal}) + "\n")
        return seal

    @classmethod
    def load(cls, path) -> "LearnedModel":
        with open(path, encoding="utf-8") as f:
            d = json.loads(f.read())
        if hashlib.sha256(_canon(d["body"]).encode()).hexdigest() != d.get("sha256"):
            raise ValueError("model file failed its integrity check (edited or corrupted); refusing to load")
        b = d["body"]
        model = {"logistic": LogisticModel, "counts": CountModel}[b["model"]["kind"]].from_dict(b["model"])
        cal = IsotonicCalibrator.from_dict(b["calibrator"]) if b["calibrator"] else None
        return cls(b["name"], model, cal, b["provenance"], b["metrics"])


def dataset_hash(rows: Sequence[Mapping[str, Any]], labels: Sequence[int]) -> str:
    h = hashlib.sha256()
    for r, y in zip(rows, labels):
        h.update(_canon({"x": r, "y": int(y)}).encode())
    return h.hexdigest()


def train_binary(name: str, rows: Sequence[Mapping[str, Any]], labels: Sequence[int], groups: Sequence[str],
                 kind: str = "logistic", test_fraction: float = 0.3, seed: int = 0, calibrate: bool = True,
                 provenance: dict | None = None, **params) -> LearnedModel:
    """Group-split, fit on train, calibrate on half of the held-out groups, report metrics on the other half (or on all
    held-out data when calibration is off). Returns a LearnedModel whose `metrics` are held-out only."""
    tr, te = group_split(groups, test_fraction, seed)
    if not tr or not te:
        raise ValueError("need at least two groups to hold some out")
    model = LogisticModel(seed=seed, **params) if kind == "logistic" else CountModel(**params)
    model.fit([rows[i] for i in tr], [labels[i] for i in tr])
    cal, ev = None, te
    if calibrate:
        cal_groups = sorted({groups[i] for i in te})
        half = set(cal_groups[: max(1, len(cal_groups) // 2)])
        ci = [i for i in te if groups[i] in half]
        ev = [i for i in te if groups[i] not in half] or ci
        if sum(labels[i] for i in ci) and sum(1 - labels[i] for i in ci):
            cal = IsotonicCalibrator().fit([model.decision(rows[i]) for i in ci], [labels[i] for i in ci])
    lm = LearnedModel(name, model, cal)
    base = sum(labels[i] for i in tr) / len(tr)
    lm.metrics = {"held_out": evaluate_binary([labels[i] for i in ev], [lm.proba(rows[i]) for i in ev], base),
                  "train_rows": len(tr), "held_out_rows": len(ev), "held_out_groups": len({groups[i] for i in ev}),
                  "split_seed": seed}
    lm.provenance = dict(provenance or {}, dataset_sha256=dataset_hash(rows, labels), rows=len(rows),
                         groups=len(set(groups)), kind=kind)
    return lm


# ----------------------------------------------------------------------------- experience records -> training data
def examples_from_experiences(records: Iterable, feature_key: str = "features", label_key: str = "label") -> tuple:
    """Experience records -> (rows, labels, groups, provenance counts). The DEV16 data rule: a record whose
    evidence_status is "generated" (e.g. produced by a language model) trains nothing unless its metadata carries
    verified_by_execution=True; such records are counted as refused."""
    rows, labels, groups = [], [], []
    counts = {"used": 0, "refused_unverified_generated": 0, "no_label": 0, "by_source": {}, "by_evidence": {}}
    for r in records:
        if r.evidence_status == "generated" and not (r.metadata or {}).get("verified_by_execution"):
            counts["refused_unverified_generated"] += 1
            continue
        if not r.outcome or label_key not in r.outcome:
            counts["no_label"] += 1
            continue
        rows.append(dict(r.observation.get(feature_key, r.observation)))
        labels.append(int(r.outcome[label_key]))
        groups.append(r.task_id)
        counts["used"] += 1
        counts["by_source"][r.source] = counts["by_source"].get(r.source, 0) + 1
        counts["by_evidence"][r.evidence_status] = counts["by_evidence"].get(r.evidence_status, 0) + 1
    return rows, labels, groups, counts
