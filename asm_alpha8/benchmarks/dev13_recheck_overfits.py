"""Re-run the faults behind DEV11's two known overfit patches through the current workflow and judge the accepted
patch with the DEV13 differential oracle. Input: benchmarks/results/benchB_*.jsonl (DEV11 raw results)."""
import glob
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "benchmarks"))
import dev11_seeded_faults as B  # noqa: E402
import dev13_oracle as O  # noqa: E402
from asm.coding import SafeTestRunner  # noqa: E402
from asm.coding.faultloc import RepairWorkflow, apply_site, ast_normal, collect_spectrum, enumerate_sites  # noqa: E402
from asm.coding.patches import apply_proposal  # noqa: E402
from asm.coding.understanding import CodeUnderstanding  # noqa: E402

recs = [json.loads(l) for f in sorted(glob.glob(str(ROOT / "benchmarks/results/benchB_*.jsonl"))) for l in open(f)]
odd = [r for r in recs if r["repair_status"] == "resolved" and (not r["restored"] or not r["truth_function_patched"])]
r = odd[int(sys.argv[1])]
runner = SafeTestRunner(timeout_seconds=60)
td = Path(tempfile.mkdtemp())
template = B.make_template(r["subject"], td)
und = CodeUnderstanding().analyze(template)
infos = {f.qname: f for f in und.functions}
ranges = {}
for f in und.functions:
    ranges.setdefault(f.path, []).append((f.qname, f.line, f.end_line))
src = (template / r["file"]).read_text()
site = next(s for s in enumerate_sites(src, r["file"], ranges[r["file"]])
            if s.line == r["line"] and s.kind == r["kind"] and s.original == r["original"] and r["option"] in s.options)
work = td / "w"
shutil.copytree(template, work)
(work / r["file"]).write_text(apply_site(src, site, r["option"]))
tests = B.SUBJECTS[r["subject"]]["tests"]
orig_sp = collect_spectrum(template, tests, runner)
d = RepairWorkflow(runner, time_budget_seconds=150).run(work, tests)
st = d.steps[0] if d.steps else {}
fixed = td / "fixed"
shutil.copytree(work, fixed)
for p in d._proposals:
    apply_proposal(fixed, p, backup=False)
restored = ast_normal((fixed / r["file"]).read_text()) == ast_normal(src)
cls = O.classify_patch(template, fixed, restored, sorted({site.function} | {s["suspect"] for s in d.steps}), infos, orig_sp)
v = st.get("verification", {})
print(json.dumps({"case": int(sys.argv[1]), "truth": site.function, "patched": [s["suspect"] for s in d.steps],
                  "status": d.status, "label": st.get("confidence"), "flags": st.get("confidence_basis"),
                  "competing": st.get("competing_patches"), "verification_available": v.get("available"),
                  "verification_target": v.get("target"), "inputs_tested": v.get("inputs_tested"),
                  "oracle": cls["class"], "oracle_detail": {q: x["status"] for q, x in cls["details"].items()}}))
