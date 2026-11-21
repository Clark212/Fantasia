from __future__ import annotations
import sqlite3
import tempfile
import unittest
from pathlib import Path

from asm import ASMEngine, __version__
from tests.test_alpha76_r3 import activate_context, trust
from tests.test_alpha78_r2 import stats_field


class Alpha78ReleaseTests(unittest.TestCase):
    def test_release_identity_and_snapshot_key(self):
        self.assertEqual(__version__, "0.4.0-alpha.7.9")
        self.assertEqual(ASMEngine.SNAPSHOT_KEY, "asm_snapshot_v0_4_0_alpha_7_9")
        self.assertEqual(ASMEngine.ALPHA77_V04_SNAPSHOT_KEY, "asm_snapshot_v0_4_0_alpha_7_7")
        self.assertEqual(ASMEngine.ALPHA76_V04_SNAPSHOT_KEY, "asm_snapshot_v0_4_0_alpha_7_6")

    def test_alpha77_snapshot_fallback_preserves_route_history_and_decision(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/"state.db"
            e=ASMEngine(path);trust(e);activate_context(e,"mig78","A",1);activate_context(e,"mig78","B",-1)
            for i in range(4):
                e.observe_procedure_route("mig78",{"mode":False},"A",evidence_id=f"a-{i}",source_id="oracle")
                e.observe_procedure_route("mig78",{"mode":True},"B",evidence_id=f"b-{i}",source_id="oracle")
            before=e.route_procedure_context("mig78",{"mode":True})
            records=e.procedure_route_evidence_status("mig78")["total_records"]
            e.save();e.close()
            con=sqlite3.connect(path)
            payload=con.execute("SELECT value FROM kv WHERE key=?",(ASMEngine.SNAPSHOT_KEY,)).fetchone()[0]
            con.execute("DELETE FROM kv WHERE key=?",(ASMEngine.SNAPSHOT_KEY,))
            con.execute("INSERT OR REPLACE INTO kv(key,value) VALUES(?,?)",(ASMEngine.ALPHA77_V04_SNAPSHOT_KEY,payload))
            con.commit();con.close()
            e=ASMEngine(path)
            after=e.route_procedure_context("mig78",{"mode":True})
            self.assertEqual(records,e.procedure_route_evidence_status("mig78")["total_records"])
            self.assertEqual((before["status"],before.get("context")),(after["status"],after.get("context")))
            e.save();e.close()
            con=sqlite3.connect(path);keys={r[0] for r in con.execute("SELECT key FROM kv WHERE key LIKE 'asm_snapshot_v0_4_0_alpha_7_%'")};con.close()
            self.assertIn(ASMEngine.SNAPSHOT_KEY,keys)
            self.assertIn(ASMEngine.ALPHA77_V04_SNAPSHOT_KEY,keys)

    def test_default_router_is_full_latent_and_alpha77_control_remains_selectable(self):
        with tempfile.TemporaryDirectory() as td:
            e=ASMEngine(Path(td)/"state.db");trust(e);activate_context(e,"m","left",1);activate_context(e,"m","right",-1)
            bad=[f"b{i}" for i in range(10)];good="good"
            for s in bad+[good]:trust(e,s)
            stats=stats_field(bad+[good],lambda a,b:.12 if a in bad and b in bad else 0.0)
            e.procedures.dependency_provider=lambda _s:{"pairwise":{},"pairwise_stats":stats,"version":900}
            for i,s in enumerate(bad):e.observe_procedure_route("m",{"signal":True},"left",evidence_id=f"b{i}",source_id=s)
            e.observe_procedure_route("m",{"signal":True},"right",evidence_id="g",source_id=good)
            alpha77=e.route_procedure_context("m",{"signal":True},epistemic_mode="full_covariance",min_support=1)
            default=e.route_procedure_context("m",{"signal":True},min_support=1)
            explicit=e.route_procedure_context("m",{"signal":True},epistemic_mode="full_latent",min_support=1)
            self.assertEqual((alpha77["status"],alpha77.get("context")),("routed","left"))
            self.assertEqual((default["status"],default.get("context")),(explicit["status"],explicit.get("context")))
            self.assertNotEqual((default["status"],default.get("context")),("routed","left"))
            e.close()

if __name__ == "__main__":
    unittest.main()
