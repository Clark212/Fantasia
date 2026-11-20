"""Append-only, provenance-aware store for verified coding procedures."""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path


class ProcedureStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def record(self, *, task_type: str, task_summary: str, procedure: list[str],
               repository_fingerprint: str, test_result: dict) -> dict:
        if not test_result.get("passed") or test_result.get("timed_out"):
            raise ValueError("only procedures followed by a passing test run can be recorded")
        if not task_type or not procedure or not repository_fingerprint:
            raise ValueError("task_type, procedure, and repository_fingerprint are required")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"timestamp": time.time(), "task_type": task_type,
                   "task_summary": task_summary[:500], "procedure": procedure,
                   "repository_fingerprint": repository_fingerprint,
                   "test_returncode": test_result.get("returncode"),
                   "test_duration_seconds": test_result.get("duration_seconds")}
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        payload["record_sha256"] = hashlib.sha256(encoded.encode()).hexdigest()
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")
            handle.flush()
        return payload

    def list_records(self) -> list[dict]:
        if not self.path.exists():
            return []
        records = []
        with self.path.open(encoding="utf-8") as handle:
            for line_no, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                record = json.loads(line)
                digest = record.pop("record_sha256", None)
                encoded = json.dumps(record, sort_keys=True, separators=(",", ":"))
                if digest != hashlib.sha256(encoded.encode()).hexdigest():
                    raise ValueError(f"procedure record integrity failure at line {line_no}")
                record["record_sha256"] = digest
                records.append(record)
        return records
