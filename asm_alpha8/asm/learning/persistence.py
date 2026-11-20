"""DEV2: durable, append-only, hash-chained experience log with audits.

Experimental; NOT wired into ASM beliefs, memory or action selection.

Guarantees (and limits):
- Append-only JSONL. Each entry carries schema version, sequence number, the previous
  entry's hash and its own hash, so edits, deletions, reordering and truncation of
  earlier entries are detected on open and by ``verify()``.
- The chain gives tamper EVIDENCE, not tamper PROOF: someone who rewrites the whole
  file and recomputes every hash cannot be detected without an externally stored head hash.
  Store ``head_hash`` from ``manifest()`` somewhere independent to close that gap.
- Duplicate experience_id or fingerprint is rejected, matching ExperienceStore.
- One process may write at a time (thread-safe inside a process). Before every append (and once
  per ``append_many`` batch) the writer checks that the file is still the one it last wrote:
    * ``integrity="full"`` (default): file identity (device+inode), size, and a SHA-256 of every
      byte already in the file. Any outside change is refused, including an edit that keeps the
      length the same and one that restores the modification time. Cost is one read of the file
      per ``append`` call, so prefer ``append_many`` for bulk loads.
    * ``integrity="metadata"`` (opt-in, O(1)): identity, size, mtime_ns, ctime_ns and a re-hash of
      the last entry. It can miss a same-length edit made inside the filesystem's timestamp
      granularity of the previous write, or an edit to an older entry on a platform whose ctime
      is not a change time (Windows). ``verify()`` and reopening always check the full chain.
  A refused log stays refused; nothing is written.
- Replacing the file (new inode), even with identical bytes, is treated as a change.
- No wall-clock data is written by this module, so identical inputs give identical hashes.
"""
from __future__ import annotations

import hashlib
import json
import os
from collections import Counter
from pathlib import Path
from threading import RLock
from typing import Any, Iterable, Iterator, Mapping

from .experience import Experience
from .ingestion import iter_records, split_records
from .store import ExperienceStore

SCHEMA_VERSION = 1
GENESIS_HASH = "0" * 64
_SAMPLE_LIMIT = 10

# Hook for future schema changes: {from_version: callable(entry_dict) -> entry_dict at from_version+1}.
# Nothing is registered yet; versions other than SCHEMA_VERSION are rejected explicitly.
MIGRATIONS: dict[int, Any] = {}


class LogCorruptionError(ValueError):
    """The log failed verification; appending is refused."""


def _canon(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False, ensure_ascii=True)


def _entry_hash(prev: str, seq: int, record: Mapping[str, Any]) -> str:
    return hashlib.sha256(f"{prev}|{seq}|{_canon(record)}".encode("ascii")).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


class _Scan:
    __slots__ = ("entries", "head", "good_offset", "torn_bytes", "errors", "ids", "fingerprints", "records",
                 "hasher", "last_line_len", "last_line_digest")

    def __init__(self) -> None:
        self.entries = 0
        self.head = GENESIS_HASH
        self.good_offset = 0
        self.torn_bytes = 0
        self.errors: list[str] = []
        self.ids: set[str] = set()
        self.fingerprints: set[str] = set()
        self.records: list[Experience] = []
        self.hasher = hashlib.sha256()
        self.last_line_len = 0
        self.last_line_digest = hashlib.sha256(b"").hexdigest()


def _scan(path: Path, *, keep_records: bool) -> _Scan:
    state = _Scan()
    if not path.exists():
        return state
    data = path.read_bytes()
    offset = 0
    while offset < len(data):
        newline = data.find(b"\n", offset)
        if newline == -1:
            state.torn_bytes = len(data) - offset
            state.errors.append(f"torn tail: {state.torn_bytes} bytes without newline at offset {offset}")
            break
        line = data[offset:newline]
        line_start = offset
        seq = state.entries + 1
        try:
            entry = json.loads(line.decode("utf-8"))
            if not isinstance(entry, dict):
                raise ValueError("entry must be an object")
            version = entry.get("schema")
            if version != SCHEMA_VERSION:
                if isinstance(version, int) and version > SCHEMA_VERSION:
                    raise ValueError(f"schema {version} was written by a newer version")
                raise ValueError(f"unsupported schema {version!r}")
            if entry.get("seq") != seq:
                raise ValueError(f"sequence gap: expected {seq}, found {entry.get('seq')!r}")
            if entry.get("prev") != state.head:
                raise ValueError("previous-hash mismatch (entry removed, reordered or edited)")
            record = entry.get("record")
            if not isinstance(record, dict):
                raise ValueError("record must be an object")
            if entry.get("hash") != _entry_hash(state.head, seq, record):
                raise ValueError("hash mismatch (entry edited)")
            experience = Experience.from_mapping(record)
            if experience.experience_id in state.ids or experience.fingerprint in state.fingerprints:
                raise ValueError("duplicate record inside log")
        except Exception as exc:  # report the first bad entry and stop: nothing after it is trustworthy
            state.errors.append(f"entry {seq} at offset {offset}: {exc}")
            state.torn_bytes = 0
            break
        state.entries = seq
        state.head = entry["hash"]
        state.ids.add(experience.experience_id)
        state.fingerprints.add(experience.fingerprint)
        if keep_records:
            state.records.append(experience)
        offset = newline + 1
        state.last_line_len = offset - line_start
        state.good_offset = offset
    state.hasher = hashlib.sha256(data[:state.good_offset])
    if state.last_line_len:
        state.last_line_digest = hashlib.sha256(data[state.good_offset - state.last_line_len:state.good_offset]).hexdigest()
    return state


class ExperienceLog:
    def __init__(self, path: str | Path, *, fsync: bool = True, repair_torn_tail: bool = False,
                 integrity: str = "full") -> None:
        if integrity not in ("full", "metadata"):
            raise ValueError("integrity must be 'full' or 'metadata'")
        self.path = Path(path)
        self._fsync = bool(fsync)
        self._integrity = integrity
        self._lock = RLock()
        self.duplicates = 0
        self.repaired_bytes = 0
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.touch()            # fix the file's identity from the start (never touches an existing file)
        state = _scan(self.path, keep_records=False)
        if state.errors:
            only_torn_tail = (len(state.errors) == 1 and state.torn_bytes > 0)
            if repair_torn_tail and only_torn_tail:
                with self.path.open("r+b") as stream:
                    stream.truncate(state.good_offset)
                self.repaired_bytes = state.torn_bytes
            else:
                raise LogCorruptionError(f"{self.path}: {'; '.join(state.errors)}")
        self._entries = state.entries
        self._head = state.head
        self._ids = state.ids
        self._fingerprints = state.fingerprints
        self._size = state.good_offset
        self._hasher = state.hasher                    # SHA-256 of every byte this writer has verified/written
        self._last_len = state.last_line_len
        self._last_digest = state.last_line_digest
        self._remember_stat(os.stat(self.path))

    @property
    def integrity(self) -> str:
        return self._integrity

    # ---- external-change guard ----------------------------------------
    def _remember_stat(self, st: os.stat_result) -> None:
        self._identity = (st.st_dev, st.st_ino)
        self._times = (st.st_mtime_ns, st.st_ctime_ns)

    def _read_exact(self, start: int, length: int) -> bytes:
        with self.path.open("rb") as stream:
            stream.seek(start)
            return stream.read(length)

    def _check_unchanged(self) -> None:
        """Raise LogCorruptionError unless the file is still exactly what this writer last saw."""
        try:
            st = os.stat(self.path)
        except FileNotFoundError:
            raise LogCorruptionError(f"{self.path}: log file is missing; reopen and verify") from None
        if (st.st_dev, st.st_ino) != self._identity:
            raise LogCorruptionError(f"{self.path}: file identity changed (replaced or moved); reopen and verify")
        if st.st_size != self._size:
            raise LogCorruptionError(
                f"{self.path}: size changed outside this writer ({st.st_size} bytes, expected {self._size}); reopen and verify")
        if self._integrity == "metadata":
            if (st.st_mtime_ns, st.st_ctime_ns) != self._times:
                raise LogCorruptionError(f"{self.path}: modification metadata changed outside this writer; reopen and verify")
            tail = self._read_exact(self._size - self._last_len, self._last_len) if self._last_len else b""
            if hashlib.sha256(tail).hexdigest() != self._last_digest:
                raise LogCorruptionError(f"{self.path}: last entry changed outside this writer; reopen and verify")
            return
        digest = hashlib.sha256()
        remaining = self._size
        with self.path.open("rb") as stream:
            while remaining:
                chunk = stream.read(min(1 << 20, remaining))
                if not chunk:
                    break
                digest.update(chunk)
                remaining -= len(chunk)
        if remaining or digest.hexdigest() != self._hasher.hexdigest():
            raise LogCorruptionError(
                f"{self.path}: existing log bytes changed outside this writer (same length); reopen and verify")

    def check_external_changes(self) -> bool:
        """True if the file is exactly what this writer last saw; raises LogCorruptionError otherwise."""
        with self._lock:
            self._check_unchanged()
            return True

    # ---- writing -------------------------------------------------------
    def append(self, experience: Experience) -> bool:
        if not isinstance(experience, Experience):
            raise TypeError("only Experience records may be logged")
        with self._lock:
            self._check_unchanged()
            return self._append_unchecked(experience)

    def _append_unchecked(self, experience: Experience) -> bool:
        if experience.experience_id in self._ids or experience.fingerprint in self._fingerprints:
            self.duplicates += 1
            return False
        record = json.loads(_canon(experience.to_dict()))
        seq = self._entries + 1
        digest = _entry_hash(self._head, seq, record)
        entry = {"schema": SCHEMA_VERSION, "seq": seq, "prev": self._head, "hash": digest, "record": record}
        payload = (_canon(entry) + "\n").encode("ascii")
        with self.path.open("ab") as stream:
            stream.write(payload)
            stream.flush()
            if self._fsync:
                os.fsync(stream.fileno())
            after = os.fstat(stream.fileno())
        self._entries, self._head, self._size = seq, digest, self._size + len(payload)
        self._hasher.update(payload)
        self._last_len, self._last_digest = len(payload), hashlib.sha256(payload).hexdigest()
        self._remember_stat(after)
        self._ids.add(experience.experience_id)
        self._fingerprints.add(experience.fingerprint)
        if after.st_size != self._size:
            raise LogCorruptionError(f"{self.path}: another writer appended concurrently; reopen and verify")
        return True

    def append_many(self, records: Iterable[Experience]) -> dict[str, int]:
        """Append a batch. The external-change check runs once, before the first write."""
        added = duplicates = 0
        with self._lock:
            self._check_unchanged()
            for record in records:
                if not isinstance(record, Experience):
                    raise TypeError("only Experience records may be logged")
                if self._append_unchecked(record):
                    added += 1
                else:
                    duplicates += 1
        return {"added": added, "duplicates": duplicates}

    def import_file(self, path: str | Path, *, source: str = "dataset") -> dict[str, int]:
        """Append a CSV/JSONL dataset. Stops at the first invalid row; earlier rows stay logged."""
        return self.append_many(iter_records(path, source=source))

    # ---- reading -------------------------------------------------------
    def __len__(self) -> int:
        with self._lock:
            return self._entries

    @property
    def head_hash(self) -> str:
        with self._lock:
            return self._head

    def records(self) -> Iterator[Experience]:
        with self._lock:
            state = _scan(self.path, keep_records=True)
        if state.errors:
            raise LogCorruptionError(f"{self.path}: {'; '.join(state.errors)}")
        return iter(state.records)

    def load_into(self, store: ExperienceStore) -> int:
        return sum(1 for record in self.records() if store.add(record))

    def verify(self) -> dict[str, Any]:
        with self._lock:
            state = _scan(self.path, keep_records=False)
            return {"ok": not state.errors, "entries": state.entries, "head_hash": state.head,
                    "errors": state.errors[:_SAMPLE_LIMIT]}

    # ---- manifest ------------------------------------------------------
    def manifest(self) -> dict[str, Any]:
        records = list(self.records())
        splits = split_records(iter(records))
        audit = audit_leakage(splits)
        independent = [r for r in records if r.evidence_status in ("observed", "labeled")]
        return {
            "schema": SCHEMA_VERSION,
            "entries": len(records),
            "head_hash": self.head_hash,
            "file_sha256": _file_sha256(self.path) if self.path.exists() else None,
            "domains": dict(sorted(Counter(r.domain for r in records).items())),
            "tasks": len({r.task_id for r in records}),
            "sources": dict(sorted(Counter(r.source for r in records).items())),
            "evidence_status": dict(sorted(Counter(r.evidence_status for r in records).items())),
            "independent_evidence": len(independent),
            "generated_or_inferred": len(records) - len(independent),
            "split_sizes": {name: len(items) for name, items in splits.items()},
            "leakage_audit": audit,
        }

    def write_manifest(self, path: str | Path) -> dict[str, Any]:
        manifest = self.manifest()
        Path(path).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return manifest


# ---- leakage audit -----------------------------------------------------
def _observation_key(record: Experience) -> str:
    return _canon({"domain": record.domain, "observation": record.observation})


def audit_leakage(splits: Mapping[str, list[Experience]], *, evaluation_splits: tuple[str, ...] = ("validation", "test")) -> dict[str, Any]:
    """Check a train/validation/test split for contamination.

    Flags: a task_id in more than one split; the same fingerprint in more than one split;
    the same (domain, observation) in train and an evaluation split (memorisation risk even
    when outcomes differ); and generated/inferred records in an evaluation split.
    """
    task_splits: dict[str, set[str]] = {}
    fingerprint_splits: dict[str, set[str]] = {}
    observation_splits: dict[str, set[str]] = {}
    weak_eval: list[str] = []
    for name, items in splits.items():
        for record in items:
            task_splits.setdefault(record.task_id, set()).add(name)
            fingerprint_splits.setdefault(record.fingerprint, set()).add(name)
            observation_splits.setdefault(_observation_key(record), set()).add(name)
            if name in evaluation_splits and record.evidence_status in ("generated", "inferred"):
                weak_eval.append(record.experience_id)
    task_overlap = sorted(t for t, s in task_splits.items() if len(s) > 1)
    fp_overlap = [f for f, s in fingerprint_splits.items() if len(s) > 1]
    obs_overlap = [o for o, s in observation_splits.items() if "train" in s and s & set(evaluation_splits)]
    report = {
        "task_overlap": len(task_overlap), "task_overlap_sample": task_overlap[:_SAMPLE_LIMIT],
        "fingerprint_overlap": len(fp_overlap),
        "train_eval_observation_overlap": len(obs_overlap),
        "weak_evidence_in_evaluation": len(weak_eval), "weak_evidence_sample": sorted(weak_eval)[:_SAMPLE_LIMIT],
    }
    report["clean"] = not (task_overlap or fp_overlap or obs_overlap or weak_eval)
    return report
