import os
import subprocess
import sys
import unittest

from asm.semantic import OnlineSemanticMap


class ReviewPatchTests(unittest.TestCase):
    def test_semantic_similarity_cache_is_behavior_preserving(self):
        sem = OnlineSemanticMap(similarity_threshold=0.0, min_observations=1)
        sem.observe(["alpha", "beta", "gamma"])
        first = sem.similar("alpha")
        second = sem.similar("alpha")
        self.assertEqual(first, second)
        self.assertIn("alpha", sem._similar_cache)

    def test_semantic_cache_invalidates_when_model_changes(self):
        sem = OnlineSemanticMap(similarity_threshold=0.0, min_observations=1)
        sem.observe(["alpha", "beta"])
        sem.similar("alpha")
        self.assertTrue(sem._similar_cache)
        sem.observe(["alpha", "gamma"])
        self.assertFalse(sem._similar_cache)
        self.assertFalse(sem._view_cache)

    def test_core_import_and_process_without_torch(self):
        code = r'''
import builtins, tempfile
from pathlib import Path
real_import = builtins.__import__
def blocked(name, globals=None, locals=None, fromlist=(), level=0):
    if name == "torch" or name.startswith("torch."):
        raise ModuleNotFoundError("blocked torch for portability test")
    return real_import(name, globals, locals, fromlist, level)
builtins.__import__ = blocked
from asm import ASMEngine, ASMConfig
import asm.transition_mechanism as tm
with tempfile.TemporaryDirectory() as td:
    engine = ASMEngine(Path(td) / "portable.db", config=ASMConfig(snapshot_every_events=999999))
    result = engine.process("Alice believes the gate is open.", training=True)
    assert isinstance(result, dict)
    assert result.get("event_id") == 1
    try:
        tm.LocalRecurrentTransitionMechanism("torch-only")
    except RuntimeError as exc:
        assert "PyTorch is required" in str(exc)
    else:
        raise AssertionError("torch-only mechanism should fail explicitly")
    engine.close()
'''
        env = dict(os.environ)
        env["PYTHONHASHSEED"] = "0"
        proc = subprocess.run(
            [sys.executable, "-c", code],
            cwd=os.path.dirname(os.path.dirname(__file__)),
            env=env,
            text=True,
            capture_output=True,
            timeout=30,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main()
