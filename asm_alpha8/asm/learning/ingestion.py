"""Streaming CSV/JSONL ingestion with stable, group-aware data splits."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Iterator, Mapping, Any
from .experience import Experience

SPLITS = {"train", "validation", "test"}


def stable_split(group_id: str, *, train: float = 0.8, validation: float = 0.1) -> str:
    if not (0 < train < 1 and 0 <= validation < 1 and train + validation < 1):
        raise ValueError("split ratios must be non-negative and sum to less than 1")
    digest = hashlib.sha256(str(group_id).encode("utf-8")).digest()
    bucket = int.from_bytes(digest[:8], "big") / (2**64)
    if bucket < train:
        return "train"
    if bucket < train + validation:
        return "validation"
    return "test"


def _decode_record(raw: Mapping[str, Any]) -> dict[str, Any]:
    item = dict(raw)
    for key in ("observation", "prediction", "outcome", "metadata"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            try:
                item[key] = json.loads(value)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON in {key}") from exc
    if "outcome" not in item and "actual_outcome" in item:
        item["outcome"] = item.pop("actual_outcome")
    item.setdefault("metadata", {})
    return item


def iter_records(path: str | Path, *, source: str = "dataset") -> Iterator[Experience]:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix in {".jsonl", ".ndjson"}:
        with path.open("r", encoding="utf-8") as stream:
            for line_no, line in enumerate(stream, 1):
                if not line.strip():
                    continue
                try:
                    raw = json.loads(line)
                    if not isinstance(raw, Mapping):
                        raise ValueError("record must be an object")
                    yield Experience.from_mapping(_decode_record(raw), source=source)
                except Exception as exc:
                    raise ValueError(f"{path}:{line_no}: {exc}") from exc
    elif suffix == ".csv":
        with path.open("r", encoding="utf-8", newline="") as stream:
            for line_no, raw in enumerate(csv.DictReader(stream), 2):
                try:
                    yield Experience.from_mapping(_decode_record(raw), source=source)
                except Exception as exc:
                    raise ValueError(f"{path}:{line_no}: {exc}") from exc
    else:
        raise ValueError("supported dataset formats are .jsonl, .ndjson and .csv")


def split_records(records: Iterator[Experience], *, group_key: str = "task_id") -> dict[str, list[Experience]]:
    result = {name: [] for name in SPLITS}
    for record in records:
        group = str(record.metadata.get(group_key, record.task_id))
        result[stable_split(group)].append(record)
    return result
