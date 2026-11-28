"""Copy raw chained record files into benchmarks/results/dev14 and write summary.json (the published numbers), computed
by the same functions the verifier uses. Usage:
  python benchmarks/dev14_publish.py <name>=<kind>:<file1>,<file2> [...]
Existing entries in summary.json are kept unless re-published under the same name.
"""
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "benchmarks"))
import dev14_verify_results as V  # noqa: E402
from asm.coding.integrity import file_sha256, verify_chain  # noqa: E402


def main():
    V.RESULTS.mkdir(parents=True, exist_ok=True)
    out = V.RESULTS / "summary.json"
    published = json.loads(out.read_text()) if out.exists() else {}
    for arg in sys.argv[1:]:
        name, rest = arg.split("=", 1)
        kind, files = rest.split(":", 1)
        dests = []
        for f in files.split(","):
            ok, probs, _ = verify_chain(f)
            if not ok:
                raise SystemExit(f"{f}: refusing to publish a broken chain: {probs[:3]}")
            d = V.RESULTS / Path(f).name
            if Path(f).resolve() != d.resolve():
                shutil.copyfile(f, d)
            dests.append(d)
        published[name] = {"kind": kind, "files": [d.name for d in dests],
                           "file_sha256": {d.name: file_sha256(d) for d in dests},
                           "summary": V.recompute(kind, dests)}
        print(name, json.dumps(published[name]["summary"])[:300])
    out.write_text(json.dumps(published, indent=1, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
