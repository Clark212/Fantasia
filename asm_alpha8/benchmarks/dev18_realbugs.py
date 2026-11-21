"""DEV18 Q3 (pre-registered; run only if gate G18-1 passed): DEV15's real-bug harness with the frozen DEV17 procedures
and DEV18 shapes learned from the 91 training fixes. Identical to dev15_realbugs.py except that every RepairWorkflow
gets knowledge=<knowledge_dev18.json> and shapes=<shapes_dev18.json> (phase 3, only after built-in operations accept
nothing). Both files' seals are checked on load. Usage:
  python benchmarks/dev18_realbugs.py evaluate <work_dir> --knowledge=<k.json> --shapes=<s.json> [dev15 options]"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "benchmarks"))
import asm.coding.faultloc as F  # noqa: E402
import dev15_realbugs as R15  # noqa: E402
from asm.coding.integrity import file_sha256  # noqa: E402
from asm.coding.knowledge import KnowledgeBase  # noqa: E402
from asm.coding.shapes import ShapeLibrary  # noqa: E402

KPATH = next(a.split("=", 1)[1] for a in sys.argv if a.startswith("--knowledge="))
SPATH = next(a.split("=", 1)[1] for a in sys.argv if a.startswith("--shapes="))
KB, LIB = KnowledgeBase.load(KPATH), ShapeLibrary.load(SPATH)
_Base = F.RepairWorkflow


class WithLearning(_Base):
    def __init__(self, *a, **k):
        k.setdefault("knowledge", KB)
        k.setdefault("shapes", LIB)
        super().__init__(*a, **k)


F.RepairWorkflow = WithLearning
R15.PREREG = ROOT / "benchmarks" / "preregistration" / "dev18_study.md"
_orig_writer = R15.ChainedWriter


def _writer(path, manifest):
    return _orig_writer(path, dict(manifest, run="dev18_realbugs_evaluate", knowledge_sha256=file_sha256(KPATH),
                                   shapes_sha256=file_sha256(SPATH), knowledge_summary=KB.summary(), shapes_summary=LIB.summary()))


R15.ChainedWriter = _writer
if __name__ == "__main__":
    sys.argv = [a for a in sys.argv if not a.startswith(("--knowledge=", "--shapes="))]
    R15.main()
