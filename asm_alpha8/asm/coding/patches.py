"""Hash-guarded, single-file patch proposals for ASM coding intelligence.

Patch application is deliberately explicit and conservative. This is not a
security boundary against malicious code already present in the repository.
"""
from __future__ import annotations

import difflib
import hashlib
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class PatchProposal:
    path: str
    expected_sha256: str | None
    replacement: str
    reason: str = ""

    @property
    def replacement_sha256(self) -> str:
        return hashlib.sha256(self.replacement.encode("utf-8")).hexdigest()

    def preview(self, current: str = "") -> str:
        return "".join(difflib.unified_diff(
            current.splitlines(keepends=True), self.replacement.splitlines(keepends=True),
            fromfile=f"a/{self.path}", tofile=f"b/{self.path}"))

    def to_dict(self) -> dict:
        data = asdict(self)
        data["replacement_sha256"] = self.replacement_sha256
        return data


class PatchError(ValueError):
    pass


def _safe_target(root: Path, relative: str) -> Path:
    rel = Path(relative)
    if rel.is_absolute() or not relative or any(p in {"..", ""} for p in rel.parts):
        raise PatchError("patch path must be a non-empty relative path without '..'")
    base = root.resolve(strict=True)
    target = base.joinpath(rel)
    # Reject symlink components, including a symlink at the final path.
    cursor = base
    for part in rel.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise PatchError("symlink paths are not patchable")
    if not target.resolve(strict=False).is_relative_to(base):
        raise PatchError("patch target escapes repository root")
    return target


def apply_proposal(root: str | Path, proposal: PatchProposal, *, backup: bool = True) -> dict:
    base = Path(root).resolve(strict=True)
    target = _safe_target(base, proposal.path)
    if not target.is_file():
        raise PatchError("target must be an existing regular file")
    raw = target.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if proposal.expected_sha256 != actual:
        raise PatchError("stale patch: target hash differs from proposal's expected hash")
    replacement = proposal.replacement.encode("utf-8")
    backup_path = None
    if backup:
        backup_dir = base / ".asm_backups"
        backup_dir.mkdir(exist_ok=True)
        backup_path = backup_dir / (target.name + "." + actual[:12] + ".bak")
        if not backup_path.exists():
            backup_path.write_bytes(raw)
    fd, tmp_name = tempfile.mkstemp(prefix=".asm_patch_", dir=str(target.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(replacement)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, target)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    return {"path": proposal.path, "old_sha256": actual,
            "new_sha256": hashlib.sha256(replacement).hexdigest(),
            "backup": str(backup_path.relative_to(base)) if backup_path else None}

class PatchProposalBuilder:
    """Build reviewable, hash-bound proposals from explicitly supplied source text."""
    @staticmethod
    def from_replacement(root: str | Path, path: str, replacement: str,
                         reason: str = "") -> PatchProposal:
        base = Path(root).resolve(strict=True)
        target = _safe_target(base, path)
        if not target.is_file():
            raise PatchError("proposal target must be an existing regular file")
        try:
            current = target.read_bytes()
            current.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise PatchError("proposal target must be UTF-8 text") from exc
        if target.suffix == ".py":
            import ast
            try:
                ast.parse(replacement, filename=path)
            except SyntaxError as exc:
                raise PatchError(f"replacement has invalid Python syntax: {exc.msg} at line {exc.lineno}") from exc
        digest = hashlib.sha256(current).hexdigest()
        return PatchProposal(path, digest, replacement, reason)
