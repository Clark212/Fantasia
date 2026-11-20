"""DEV16 tests: the learning engine, fix patterns, learned candidate ranking, and the data pipeline (generator +
verifier)."""
import ast
import http.server
import json
import random
import shutil
import subprocess
import sys
import tempfile
import textwrap
import threading
import unittest
from pathlib import Path

from asm.coding.faultloc import RepairWorkflow, Suspect, generate_candidates
from asm.coding.learned import CandidateRanker, candidate_features
from asm.coding.patterns import PatternLibrary, edit_signature, in_repair_space, signature_key
from asm.learning.engine import (CountModel, IsotonicCalibrator, LearnedModel, LogisticModel, evaluate_binary,
                                 evaluate_ranking, examples_from_experiences, group_split, train_binary)
from asm.learning.experience import Experience

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "benchmarks"))


def synthetic(seed=1, groups=40, per=50):
    rng = random.Random(seed)
    rows, labels, gs = [], [], []
    for g in range(groups):
        for _ in range(per):
            kind, s = rng.choice(["compare", "arith", "name", "guard"]), rng.random()
            rows.append({"kind": kind, "line_score": s, "noise": rng.choice("abcdefgh")})
            labels.append(int(rng.random() < 0.05 + 0.6 * (kind == "compare") * s))
            gs.append(f"g{g}")
    return rows, labels, gs


# ================================================================================ learning engine
class EngineTests(unittest.TestCase):
    def test_models_learn_a_real_signal_and_beat_the_base_rate_on_held_out_groups(self):
        rows, labels, groups = synthetic()
        for kind in ("logistic", "counts"):
            m = train_binary("t", rows, labels, groups, kind=kind).metrics["held_out"]
            self.assertLess(m["log_loss"], m["log_loss_baseline"], kind)
            self.assertLess(m["brier"], m["brier_baseline"], kind)
            self.assertGreater(m["auc"], 0.7, kind)

    def test_no_signal_gives_no_skill(self):
        rng = random.Random(5)
        rows = [{"x": rng.choice("abcd")} for _ in range(2000)]
        labels = [int(rng.random() < 0.2) for _ in rows]
        m = train_binary("t", rows, labels, [f"g{i % 40}" for i in range(2000)]).metrics["held_out"]
        self.assertLess(abs(m["auc"] - 0.5), 0.1)

    def test_incremental_learning_moves_predictions(self):
        m = LogisticModel(seed=0)
        before = m.predict_proba({"kind": "compare"})
        for _ in range(30):
            m.partial_fit([{"kind": "compare"}, {"kind": "arith"}], [1, 0])
        self.assertGreater(m.predict_proba({"kind": "compare"}), before + 0.3)
        self.assertLess(m.predict_proba({"kind": "arith"}), 0.3)

    def test_group_split_never_shares_a_group(self):
        groups = [f"p{i % 7}" for i in range(500)]
        tr, te = group_split(groups, 0.3, seed=3)
        self.assertFalse({groups[i] for i in tr} & {groups[i] for i in te})
        self.assertEqual(len(tr) + len(te), 500)
        self.assertEqual(group_split(groups, 0.3, seed=3), (tr, te))  # deterministic

    def test_isotonic_is_monotone_smoothed_and_never_certain(self):
        c = IsotonicCalibrator().fit([0.1, 0.2, 0.3, 0.4, 0.5, 0.6], [0, 0, 1, 0, 1, 1])
        ys = [c(x) for x in (0.0, 0.15, 0.35, 0.45, 0.9)]
        self.assertEqual(ys, sorted(ys))
        self.assertTrue(all(0 < y < 1 for y in ys))

    def test_ranking_metrics(self):
        groups = [[(0.9, False, 0), (0.1, True, 1)], [(0.2, False, 0), (0.8, True, 1)], [(0.5, False, 0)]]
        r = evaluate_ranking(groups)
        self.assertEqual(r["tasks_without_true_item"], 1)
        self.assertEqual(r["learned"]["top1"], 1)
        self.assertEqual(r["given_order"]["top1"], 0)
        self.assertEqual((r["improved"], r["worsened"]), (1, 0))

    def test_binary_metrics_report_the_baseline(self):
        m = evaluate_binary([0, 1, 0, 1], [0.1, 0.9, 0.2, 0.8], 0.5)
        self.assertEqual(m["auc"], 1.0)
        self.assertLess(m["log_loss"], m["log_loss_baseline"])

    def test_sealed_model_round_trip_and_tamper_refusal(self):
        rows, labels, groups = synthetic(groups=10, per=30)
        lm = train_binary("t", rows, labels, groups)
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "m.json"
            lm.save(p)
            self.assertEqual(LearnedModel.load(p).proba(rows[3]), lm.proba(rows[3]))
            d = json.loads(p.read_text())
            d["body"]["metrics"]["held_out"]["auc"] = 0.99
            p.write_text(json.dumps(d))
            with self.assertRaises(ValueError):
                LearnedModel.load(p)
        for M in (LogisticModel, CountModel):
            m = M().fit(rows[:200], labels[:200])
            self.assertEqual(M.from_dict(json.loads(json.dumps(m.to_dict()))).decision(rows[0]), m.decision(rows[0]))

    def test_unverified_generated_experience_never_trains(self):
        def exp(i, status, meta):
            return Experience(f"e{i}", "dataset", "coding", f"t{i % 3}", {"features": {"k": "a"}}, None,
                              {"label": i % 2}, status, 0.0, meta)
        recs = [exp(0, "generated", {}), exp(1, "generated", {"verified_by_execution": True}), exp(2, "observed", {})]
        rows, labels, groups, counts = examples_from_experiences(recs)
        self.assertEqual(counts["used"], 2)
        self.assertEqual(counts["refused_unverified_generated"], 1)

    def test_features_reject_non_finite_and_unknown_types(self):
        m = LogisticModel()
        with self.assertRaises(ValueError):
            m.predict_proba({"x": float("nan")})
        with self.assertRaises(TypeError):
            m.predict_proba({"x": object()})


# ================================================================================ patterns
class PatternTests(unittest.TestCase):
    def test_signatures_of_common_fix_shapes(self):
        self.assertEqual(edit_signature("def f(a):\n    return a < 3\n", "def f(a):\n    return a <= 3\n"),
                         ["Compare.Lt->Compare.LtE"])
        self.assertEqual(edit_signature("def f(a, b):\n    return a\n", "def f(a, b):\n    return b\n"), ["Name->Name"])
        wrap = edit_signature("def f(x):\n    x.pop()\n", "def f(x):\n    try:\n        x.pop()\n    except IndexError:\n        pass\n")
        self.assertEqual(wrap, ["wrap:Try(IndexError)"])
        guard = edit_signature("def f(x):\n    return x.y\n", "def f(x):\n    if x is None:\n        return None\n    return x.y\n")
        self.assertEqual(guard, ["insert:If[Return]"])
        self.assertEqual(edit_signature("def f():\n    return 'a'\n", "def f():\n    return 'b'\n"), ["Const.str->Const.str"])

    def test_library_report_and_repair_space(self):
        lib = PatternLibrary()
        buggy = "def f(a):\n    return a < 3\n"
        ok, fam, _ = in_repair_space(buggy, "def f(a):\n    return a <= 3\n", "m.py", "m.f", [("m.f", 1, 2)])
        self.assertEqual((ok, fam), (True, "single_site"))
        no, _, _ = in_repair_space("def f():\n    return 'a'\n", "def f():\n    return 'b'\n", "m.py", "m.f", [("m.f", 1, 2)])
        self.assertFalse(no)  # string edits are outside ASM's repair space
        lib.add("p1", buggy, "def f(a):\n    return a <= 3\n", True, "single_site")
        lib.add("p2", "def f():\n    return 'a'\n", "def f():\n    return 'b'\n", False, None)
        rep = lib.report()
        self.assertEqual((rep["pairs"], rep["in_repair_space"], rep["coverage_checked"]), (2, 1, 2))
        self.assertEqual(rep["unreachable_top_signatures"][0][0], signature_key(["Const.str->Const.str"]))


# ================================================================================ ranking in the workflow
SRC = "def f(a, b):\n    x = a + b\n    y = x * 2\n    return y - 1\n"


class _Fixed:  # a stand-in model with a chosen preference
    def __init__(self, prefer):
        self.prefer = prefer

    def score(self, feats):
        return 1.0 if self.prefer(feats) else 0.0


class RankerTests(unittest.TestCase):
    def cands(self):
        return generate_candidates(SRC, "m.py", Suspect("m.f", "m.py", 1, 4, 1.0, {}, []), [("m.f", 1, 4)],
                                   {"m.py": {2: 0.5, 3: 0.9, 4: 0.4}})

    def test_every_candidate_carries_metadata(self):
        for c in self.cands() + generate_candidates(SRC, "m.py", Suspect("m.f", "m.py", 1, 4, 1.0, {}, []), [("m.f", 1, 4)],
                                                    {"m.py": {2: 0.5, 3: 0.9, 4: 0.4}}, extended=True):
            self.assertIn("family", c.meta)
            self.assertIn("line_rank", c.meta)
            candidate_features(c.meta, {})  # must not raise

    def test_rerank_is_stable_and_follows_the_model(self):
        cs = self.cands()
        r = CandidateRanker(_Fixed(lambda f: f["kind"] == "arith" and "line_rank" in f and f["line_rank"] == 3))
        out = r.rerank(cs, {})
        self.assertEqual(sorted(map(id, out)), sorted(map(id, cs)))
        self.assertEqual((out[0].meta["kind"], out[0].meta["line_rank"]), ("arith", 3))  # the one match moves to the front
        rest = [c for c in out if not (c.meta["kind"] == "arith" and c.meta["line_rank"] == 3)]
        self.assertEqual(rest, [c for c in cs if c in rest])  # untouched candidates keep their relative order

    def _repo(self):
        td = tempfile.TemporaryDirectory()
        root = Path(td.name)
        (root / "m.py").write_text("def g(a, b, c):\n    x = a + b\n    y = x * c\n    z = y + a\n    return z + 4\n")
        (root / "tests").mkdir()
        (root / "tests/test_m.py").write_text("from m import g\ndef test_1(): assert g(1, 2, 3) == 15\n"
                                              "def test_2(): assert g(0, 0, 0) == 5\n")
        return td, root

    def test_no_ranker_is_dev15_and_a_ranker_changes_only_the_order(self):
        td, root = self._repo()
        with td:
            d0 = RepairWorkflow().run(root)
            d1 = RepairWorkflow(ranker=CandidateRanker(_Fixed(lambda f: f["kind"] == "const"))).run(root)
            self.assertEqual(d0.status, "resolved")
            self.assertEqual((d1.status, d1.diff), (d0.status, d0.diff))  # one true fix: order cannot change it
            self.assertTrue(any("candidate order learned" in n for n in d1.notes))
            self.assertFalse(any("candidate order learned" in n for n in d0.notes))

    def test_ranker_never_moves_phase_two_ahead_of_phase_one(self):
        seen = []

        class Spy:
            def score(self, feats):
                seen.append(feats["phase"])
                return 10.0 if feats["family"] != "single_site" else 0.0  # would put DEV15 families first if it could
        td, root = self._repo()
        with td:
            d = RepairWorkflow(ranker=CandidateRanker(Spy())).run(root)
        self.assertEqual(d.status, "resolved")
        self.assertEqual(d.steps[0]["edit_family"], "single_site")
        self.assertEqual(set(seen), {1})  # phase 1 resolved it: phase 2 was never even generated


# ================================================================================ data pipeline
import generate_pairs as G  # noqa: E402


class GeneratorTests(unittest.TestCase):
    ORIG = "def f(xs, n):\n    \"\"\"Doc.\"\"\"\n    return xs[:n]\n"

    def test_reply_checks(self):
        self.assertIsNone(G.check_reply(self.ORIG, self.ORIG.replace("xs[:n]", "xs[:n - 1]")))
        self.assertEqual(G.check_reply(self.ORIG, self.ORIG), "no change to the code")
        self.assertEqual(G.check_reply(self.ORIG, self.ORIG.replace('"""Doc."""', '"""Other."""')), "no change to the code")
        self.assertEqual(G.check_reply(self.ORIG, self.ORIG.replace("(xs, n)", "(xs, m)")), "function name or parameters changed")
        self.assertIn("comments", G.check_reply(self.ORIG, self.ORIG.replace("xs[:n]", "xs[:n - 1]  # bug here")))
        self.assertEqual(G.check_reply(self.ORIG, "def f(xs, n:\n"), "reply is not valid Python")
        self.assertIn("exactly one function", G.check_reply(self.ORIG, "import os\n" + self.ORIG))
        self.assertEqual(G.extract_code("Sure!\n```python\nx = 1\n```\nbye"), "x = 1\n")

    def test_end_to_end_against_a_fake_ollama_and_resume(self):
        """The real script, run as a subprocess, against a local fake of Ollama's HTTP API and a pre-filled cache."""
        import dev16_subjects as S
        manifest = json.loads((ROOT / "tools" / "dev16_subjects.json").read_text())
        subj = next(s for s in manifest["subjects"] if s["name"] == "parse")
        subj = dict(subj, functions=subj["functions"][:3])
        try:
            sdist = S.sdist_file("parse")
        except SystemExit:
            self.skipTest("parse sdist not available (set ASM_INDEP_DIR)")

        class Fake(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, obj):
                body = json.dumps(obj).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                self._send({"models": [{"name": "fake:1b", "digest": "abc123"}]})

            def do_POST(self):
                req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                src = req["prompt"].rsplit("```python\n", 1)[1].rsplit("\n```", 1)[0]
                tree = ast.parse(src)
                for n in ast.walk(tree):  # deterministic "bug": flip the first comparison or constant it finds
                    if isinstance(n, ast.Compare):
                        n.ops[0] = ast.NotEq() if not isinstance(n.ops[0], ast.NotEq) else ast.Eq()
                        break
                    if isinstance(n, ast.Constant) and isinstance(n.value, int) and not isinstance(n.value, bool):
                        n.value += 1
                        break
                self._send({"response": "```python\n" + ast.unparse(tree) + "\n```"})
        srv = http.server.HTTPServer(("127.0.0.1", 0), Fake)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            with tempfile.TemporaryDirectory() as td:
                td = Path(td)
                (td / "m.json").write_text(json.dumps({"manifest_version": 1, "subjects": [subj]}))
                (td / "cache").mkdir()
                shutil.copy(sdist, td / "cache" / subj["sdist_filename"])
                cmd = [sys.executable, str(ROOT / "tools" / "generate_pairs.py"), "--model", "fake:1b", "--out",
                       str(td / "p.jsonl"), "--manifest", str(td / "m.json"), "--host", f"http://127.0.0.1:{srv.server_port}",
                       "--per-function", "2", "--cache", str(td / "cache")]
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                self.assertEqual(r.returncode, 0, r.stderr)
                recs = [json.loads(l) for l in (td / "p.jsonl").read_text().splitlines()]
                self.assertEqual(len(recs), 6)
                self.assertTrue(all(x["model_digest"] == "abc123" and x["sdist_sha256"] == subj["sdist_sha256"] for x in recs))
                self.assertTrue(any(x["accepted_locally"] for x in recs))
                r2 = subprocess.run(cmd, capture_output=True, text=True, timeout=120)  # resume: nothing new to do
                self.assertEqual(len((td / "p.jsonl").read_text().splitlines()), 6, r2.stdout)
        finally:
            srv.shutdown()

    def test_manifest_has_only_training_subjects(self):
        import dev16_subjects as S
        manifest = json.loads((ROOT / "tools" / "dev16_subjects.json").read_text())
        names = {s["name"] for s in manifest["subjects"]}
        self.assertTrue(names <= set(S.TRAINING))
        self.assertFalse({s["pypi_name"].lower() for s in manifest["subjects"]} & S.EVALUATION_PROJECTS)


class VerifierTests(unittest.TestCase):
    def test_buggy_method_is_placed_at_its_indentation(self):
        from dev16_verify_pairs import build_buggy
        orig = "class C:\n    def m(self, x):\n        return x + 1\n\n    def k(self):\n        return 2\n"
        rec = {"line": 2, "end_line": 3, "indent": "    ", "buggy_function": "def m(self, x):\n    return x - 1\n"}
        new, fn = build_buggy(orig, rec)
        self.assertEqual(fn, "    def m(self, x):\n        return x + 1\n")
        self.assertEqual(new, orig.replace("x + 1", "x - 1"))
        ast.parse(new)


if __name__ == "__main__":
    unittest.main()
