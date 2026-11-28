"""DEV14 evidence-chain integrity.

Purpose: every conclusion DEV14 publishes should be re-checkable by someone who does not trust the author.
- PROVENANCE: interpreter, platform, pytest version and a content hash of the `asm.coding` source that produced a result.
- DOSSIER SEALING: a repair dossier carries a hash chain over its accepted steps and a content hash over everything else;
  `verify_dossier` recomputes both. `RepairWorkflow.apply_fix` refuses a dossier whose content no longer matches its seal
  (e.g. a "partial" status edited to "resolved").
- CHAINED RECORDS: benchmark results are JSONL where each line carries the hash of the previous line; the first line links
  to a run manifest (provenance, arguments, input hashes, pre-registration hash). Edits, deletions, reordering and
  truncation are detected.

Honest scope: these are SHA-256 hash chains, not signatures. They detect accidental or casual modification and make
results reproducible and auditable; someone who can rewrite a whole file can also recompute its hashes. Publishing the
final hash elsewhere (e.g. in a message or the release manifest) is what anchors a chain.
"""
from __future__ import annotations

import hashlib
import json
import platform
import sys
import time
from pathlib import Path

SCHEMA = 1
GENESIS = "0" * 64


def canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def sha256_obj(obj) -> str:
    return hashlib.sha256(canonical(obj)).hexdigest()


def code_hash(package_dir: str | Path | None = None) -> str:
    """Content hash of every .py file of the coding package (path + bytes), order-independent of the filesystem."""
    base = Path(package_dir) if package_dir else Path(__file__).resolve().parent
    h = hashlib.sha256()
    for p in sorted(base.rglob("*.py")):
        if "__pycache__" in p.parts:
            continue
        h.update(p.relative_to(base).as_posix().encode() + b"\0" + hashlib.sha256(p.read_bytes()).digest())
    return h.hexdigest()


def environment_provenance() -> dict:
    try:
        import pytest
        pytest_version = pytest.__version__
    except Exception:  # pragma: no cover - pytest missing
        pytest_version = None
    return {"python": platform.python_version(), "implementation": platform.python_implementation(),
            "platform": platform.platform(), "pytest": pytest_version, "asm_coding_sha256": code_hash(),
            "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}


# ------------------------------------------------------------------------------------------- dossiers
def step_chain(steps: list) -> list:
    chain, prev = [], GENESIS
    for st in steps:
        prev = hashlib.sha256(prev.encode() + canonical(st)).hexdigest()
        chain.append(prev)
    return chain


def seal(body: dict, provenance: dict | None = None) -> dict:
    """Return the integrity block for a dossier body (the dict WITHOUT an 'integrity' key)."""
    body = {k: v for k, v in body.items() if k != "integrity"}
    prov = provenance or environment_provenance()
    return {"schema": SCHEMA, "provenance": prov, "step_chain": step_chain(body.get("steps", [])),
            "content_sha256": sha256_obj({"body": body, "provenance": prov})}


def verify_dossier(d: dict) -> tuple:
    """(ok, problems). Recomputes the step chain and the content hash of a dossier dict that has an 'integrity' block."""
    integ = d.get("integrity")
    if not isinstance(integ, dict):
        return False, ["no integrity block"]
    problems = []
    if integ.get("schema") != SCHEMA:
        problems.append(f"unknown integrity schema {integ.get('schema')!r}")
    body = {k: v for k, v in d.items() if k != "integrity"}
    expected_chain = step_chain(body.get("steps", []))
    got_chain = integ.get("step_chain", [])
    if len(got_chain) != len(expected_chain):
        problems.append(f"step count changed: sealed {len(got_chain)}, now {len(expected_chain)}")
    for i, (a, b) in enumerate(zip(expected_chain, got_chain)):
        if a != b:
            problems.append(f"step {i} differs from its sealed hash")
            break
    if sha256_obj({"body": body, "provenance": integ.get("provenance")}) != integ.get("content_sha256"):
        problems.append("dossier content differs from its seal")
    return (not problems), problems


# ------------------------------------------------------------------------------------- chained records
class ChainedWriter:
    """Append-only JSONL with a hash chain. Line 0 is the run manifest; every later line links to the previous one."""

    def __init__(self, path: str | Path, manifest: dict | None = None):
        self.path = Path(path)
        if self.path.exists() and self.path.stat().st_size:
            ok, problems, last = verify_chain(self.path)
            if not ok:
                raise ValueError(f"refusing to append to a broken chain: {problems[:2]}")
            self._prev = last
        else:
            if manifest is None:
                raise ValueError("a new chained file needs a run manifest")
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._prev = GENESIS
            self._write({"_kind": "manifest", **manifest})

    def _write(self, rec: dict) -> str:
        rec = {k: v for k, v in rec.items() if k not in {"_prev", "_sha"}}
        rec["_prev"] = self._prev
        rec["_sha"] = sha256_obj(rec)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, sort_keys=True) + "\n")
            fh.flush()
        self._prev = rec["_sha"]
        return self._prev

    def append(self, rec: dict) -> str:
        return self._write(rec)

    @property
    def head(self) -> str:
        return self._prev


def verify_chain(path: str | Path) -> tuple:
    """(ok, problems, last_hash). Detects edited, deleted, inserted, reordered and truncated (torn) lines."""
    problems, prev = [], GENESIS
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    if not lines:
        return False, ["empty file"], GENESIS
    for i, line in enumerate(lines):
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            problems.append(f"line {i + 1}: not valid JSON (torn or edited)")
            break
        if i == 0 and rec.get("_kind") != "manifest":
            problems.append("line 1 is not a run manifest")
        if rec.get("_prev") != prev:
            problems.append(f"line {i + 1}: does not link to the previous line (deleted, inserted or reordered)")
            break
        body = {k: v for k, v in rec.items() if k != "_sha"}
        if sha256_obj(body) != rec.get("_sha"):
            problems.append(f"line {i + 1}: content does not match its hash (edited)")
            break
        prev = rec["_sha"]
    return (not problems), problems, prev


def read_records(path: str | Path) -> tuple:
    """(manifest, records) from a verified chained file; raises if the chain is broken."""
    ok, problems, _ = verify_chain(path)
    if not ok:
        raise ValueError(f"{path}: broken evidence chain: {problems}")
    rows = [json.loads(l) for l in Path(path).read_text(encoding="utf-8").splitlines()]
    strip = lambda r: {k: v for k, v in r.items() if k not in {"_prev", "_sha", "_kind"}}  # noqa: E731
    return strip(rows[0]), [strip(r) for r in rows[1:]]


def file_sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
