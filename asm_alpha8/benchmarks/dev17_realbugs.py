"""DEV17 Q3 (pre-registered; run only if gate G17-1 passed): DEV15's real-bug harness with the frozen knowledge base
learned from the training projects' history. Identical to dev15_realbugs.py except that every RepairWorkflow gets
`knowledge=<knowledge_history.json>` (phase 3: learned procedures, only after built-in operations accept nothing).
The knowledge file's seal is checked on load. Usage:
  python benchmarks/dev17_realbugs.py evaluate <work_dir> --knowledge=<knowledge_history.json> [dev15 options]"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "benchmarks"))
import asm.coding.faultloc as F  # noqa: E402
import dev15_realbugs as R15  # noqa: E402
from asm.coding.integrity import file_sha256  # noqa: E402
from asm.coding.knowledge import KnowledgeBase  # noqa: E402

KPATH = next(a.split("=", 1)[1] for a in sys.argv if a.startswith("--knowledge="))
KB = KnowledgeBase.load(KPATH)
_Base = F.RepairWorkflow


class WithKnowledge(_Base):
    def __init__(self, *a, **k):
        k.setdefault("knowledge", KB)
        super().__init__(*a, **k)


F.RepairWorkflow = WithKnowledge  # dev15_realbugs imports RepairWorkflow from faultloc inside stage_evaluate
R15.PREREG = ROOT / "benchmarks" / "preregistration" / "dev17_study.md"
_orig_writer = R15.ChainedWriter


def _writer(path, manifest):
    manifest = dict(manifest, run="dev17_realbugs_evaluate", knowledge_sha256=file_sha256(KPATH),
                    knowledge_summary=KB.summary())
    return _orig_writer(path, manifest)


R15.ChainedWriter = _writer
if __name__ == "__main__":
    sys.argv = [a for a in sys.argv if not a.startswith("--knowledge=")]
    R15.main()
