"""Write ALPHA8_CODING_DEV15_MANIFEST.json: sha256 of every file DEV15 added or changed relative to DEV14, plus the
code hash and the published-results summary hash. Usage: python benchmarks/dev14_make_manifest.py <dev14_dir> <extra.json>"""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from asm.coding.integrity import code_hash  # noqa: E402

SKIP = {"__pycache__", ".pytest_cache"}


def files(base: Path) -> dict:
    out = {}
    for p in sorted(base.rglob("*")):
        if p.is_file() and not (SKIP & set(p.relative_to(base).parts)) and p.suffix != ".pyc":
            out[p.relative_to(base).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def main():
    old, extra = files(Path(sys.argv[1])), json.loads(Path(sys.argv[2]).read_text())
    new = files(ROOT)
    changed = {k: v for k, v in new.items() if old.get(k) != v and k != "ALPHA8_CODING_DEV15_MANIFEST.json"}
    removed = sorted(set(old) - set(new))
    m = dict(extra, asm_coding_sha256=code_hash(), changed_or_added=len(changed), removed=removed, sha256=changed)
    (ROOT / "ALPHA8_CODING_DEV15_MANIFEST.json").write_text(json.dumps(m, indent=1, sort_keys=True) + "\n")
    print(len(changed), "files;", "removed:", removed)


if __name__ == "__main__":
    main()
