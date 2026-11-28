"""DEV31 development check: the learned libraries' phase-3 candidates for real (source, span) inputs, computed with the
asm package under <asm_root>. Run with HEAD's package and with the working tree's, then compare (timings aside)."""
import json, sys, time, types
from pathlib import Path
asm_root, inputs, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
sys.path.insert(0, str(asm_root))
from asm.coding.faultloc import _problem_context
from asm.coding.knowledge import KnowledgeBase
from asm.coding.shapes import ShapeLibrary
from asm.coding.steps import StepLibrary
LIB = Path("/home/user/Fantasia/asm_alpha8/benchmarks/results/dev20")
kb, sl, st = (KnowledgeBase.load(LIB / "knowledge_dev20.json"), ShapeLibrary.load(LIB / "shapes_dev20.json"),
              StepLibrary.load(LIB / "steps_dev20.json"))
with open(out, "w") as f:
    for line in open(inputs):
        x = json.loads(line)
        tree, span = Path(x["tree"]), tuple(x["span"])
        source = (tree / x["path"]).read_text()
        t = time.time()
        ctx = _problem_context(tree, types.SimpleNamespace(failing=x["failing"], failures={}), source)
        rec = {"id": x["id"], "knowledge": [(c.replacement, c.reason) for c in kb.candidates_for(source, x["path"], span, limit=30)],
               "shapes": sl.candidates_for(source, x["path"], span, ctx, limit=20, as_candidates=False),
               "steps": st.candidates_for(source, x["path"], span, ctx, limit=30, as_candidates=False)}
        f.write(json.dumps({**rec, "seconds": round(time.time() - t, 2)}, default=str) + "\n")
        f.flush()
