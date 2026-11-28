"""Run a script with ProcedureCortex options forced, e.g. to reproduce alpha 7.x release benchmarks that predate DEV3.3's
default extrapolation guard: python tools/with_cortex_options.py extrapolation_guard=off benchmark_v040a73.py [args]
Options are forced even when a caller (ASMEngine, from ASMConfig) passes them explicitly."""
import runpy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from asm import procedure_cortex as P  # noqa: E402

forced = dict(kv.split("=", 1) for kv in sys.argv[1].split(",") if kv)
_init = P.ProcedureCortex.__init__


def _patched(self, *args, **kwargs):
    _init(self, *args, **{**kwargs, **forced})


P.ProcedureCortex.__init__ = _patched
sys.argv = sys.argv[2:]
runpy.run_path(sys.argv[0], run_name="__main__")
