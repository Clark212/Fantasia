from __future__ import annotations
import sqlite3
import tempfile
import unittest
from pathlib import Path

from asm import ASMEngine, __version__
from tests.test_alpha75_parallel import trust, activate_context


class Alpha76ReleaseTests(unittest.TestCase):
    def test_release_identity_and_snapshot_key(self):
        self.assertEqual(__version__, "0.4.0-alpha.7.9")
        self.assertEqual(ASMEngine.SNAPSHOT_KEY, "asm_snapshot_v0_4_0_alpha_7_9")
        self.assertEqual(ASMEngine.ALPHA76_V04_SNAPSHOT_KEY, "asm_snapshot_v0_4_0_alpha_7_6")
        self.assertEqual(ASMEngine.ALPHA74_V04_SNAPSHOT_KEY, "asm_snapshot_v0_4_0_alpha_7_4")

    def test_alpha74_snapshot_fallback_preserves_routing_state(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "state.db"
            e = ASMEngine(path)
            trust(e)
            activate_context(e, "mig76", "A", lambda x: x + 1)
            activate_context(e, "mig76", "B", lambda x: x - 1)
            for i in range(4):
                e.observe_procedure_route("mig76", {"mode": False}, "A", evidence_id=f"a-{i}", source_id="oracle")
                e.observe_procedure_route("mig76", {"mode": True}, "B", evidence_id=f"b-{i}", source_id="oracle")
            before = e.route_procedure_context("mig76", {"mode": True})
            records = e.procedure_route_evidence_status("mig76")["total_records"]
            e.close()

            con = sqlite3.connect(path)
            payload = con.execute("SELECT value FROM kv WHERE key=?", (ASMEngine.SNAPSHOT_KEY,)).fetchone()[0]
            con.execute("DELETE FROM kv WHERE key=?", (ASMEngine.SNAPSHOT_KEY,))
            con.execute("INSERT OR REPLACE INTO kv(key,value) VALUES(?,?)", (ASMEngine.ALPHA74_V04_SNAPSHOT_KEY, payload))
            con.commit(); con.close()

            e = ASMEngine(path)
            after = e.route_procedure_context("mig76", {"mode": True})
            self.assertEqual(records, e.procedure_route_evidence_status("mig76")["total_records"])
            self.assertEqual((before["status"], before["context"]), (after["status"], after["context"]))
            e.close()

            con = sqlite3.connect(path)
            keys = {r[0] for r in con.execute("SELECT key FROM kv WHERE key LIKE 'asm_snapshot_v0_4_0_alpha_7_%'")}
            con.close()
            self.assertIn(ASMEngine.SNAPSHOT_KEY, keys)
            self.assertIn(ASMEngine.ALPHA74_V04_SNAPSHOT_KEY, keys)


if __name__ == "__main__":
    unittest.main()
