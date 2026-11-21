import math
import tempfile
import unittest
from pathlib import Path

from asm import ASMEngine, ASMConfig, __version__
from asm.language_core import create_language_core


class TestASM020Alpha2(unittest.TestCase):
    def make_engine(self, config=None):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        asm = ASMEngine(Path(td.name) / "asm.db", config=config)
        self.addCleanup(asm.close)
        return asm

    def test_version(self):
        self.assertEqual(__version__, '0.4.0-alpha.7.9')

    def test_default_recurrent_reader_loads_frozen_weights(self):
        asm = self.make_engine()
        status = asm.language_core_status()
        self.assertEqual(status["backend"], "recurrent-reader")
        self.assertTrue(status["ready"])
        self.assertTrue(status["weights_frozen"])
        self.assertGreaterEqual(status["validation_accuracy"], 0.80)
        self.assertEqual(status["capabilities"]["embedding_dims"], 96)

    def test_recurrent_embedding_is_real_normalized_hidden_state(self):
        asm = self.make_engine()
        a = asm.embed_text("I tried analogy and it failed")
        b = asm.embed_text("I tried analogy and it failed")
        self.assertEqual(a, b)
        self.assertEqual(len(a), 96)
        self.assertAlmostEqual(math.sqrt(sum(x*x for x in a)), 1.0, places=5)
        self.assertTrue(any(abs(x) > 1e-6 for x in a))

    def test_high_confidence_neural_intent_updates_self_model(self):
        asm = self.make_engine()
        before = asm.capability("reasoning")["attempts"]
        result = asm.process("I tried analogy and it failed", training=True)
        after = asm.capability("reasoning")["attempts"]
        self.assertEqual(after, before + 1)
        self.assertEqual(result["language_core"]["metadata"]["intent"], "self_outcome")
        self.assertEqual(len(result["language_core"]["accepted"]), 1)
        self.assertEqual(result["language_core"]["accepted"][0]["source"], "recurrent-reader")

    def test_uncertain_neural_read_defers_to_native_without_double_write(self):
        asm = self.make_engine()
        text = "Alice suspects Bob thinks the key is hidden"
        result = asm.process(text, training=True)
        state = asm.nested_belief(["Alice", "Bob"], "key is hidden")
        self.assertTrue(state["truth"])
        self.assertEqual(state["observations"], 1)
        # Current frozen reader is intentionally uncertain on this harder case.
        self.assertLess(result["language_core"]["metadata"]["intent_confidence"], 0.80)
        self.assertEqual(result["language_core"]["accepted"], [])

    def test_neural_embedding_enters_seismic_graph(self):
        asm = self.make_engine()
        asm.process("I tried simulation and it worked", training=True)
        self.assertTrue(any(k.startswith("LCORE:EMB:") for k in asm.field.nodes))
        self.assertTrue(any(k == "LCORE:INTENT:SELF_OUTCOME" for k in asm.field.nodes))

    def test_alpha2_writer_does_not_fake_learned_generation(self):
        asm = self.make_engine()
        out = asm.generate_text("summarize current focus")
        self.assertEqual(out["backend"], "recurrent-reader")
        self.assertFalse(out["metadata"]["learned_generation"])
        self.assertEqual(out["metadata"]["generation_stage"], "deferred")

    def test_rwkv7_backend_reports_missing_runtime_or_checkpoint_cleanly(self):
        cfg = ASMConfig(language_core_backend="rwkv7", rwkv7_model_path="/definitely/missing/model.pth")
        asm = self.make_engine(cfg)
        status = asm.language_core_status()
        self.assertEqual(status["backend"], "rwkv7")
        self.assertFalse(status["ready"])
        result = asm.process("practice improves skill", training=True)
        self.assertEqual(result["language_core"]["backend"], "fallback")
        self.assertEqual(result["language_core"]["metadata"]["failover_from"], "rwkv7")

    def test_registered_backends_include_recurrent_and_rwkv7(self):
        from asm import available_language_cores
        names = available_language_cores()
        self.assertIn("recurrent", names)
        self.assertIn("rwkv7", names)
        self.assertIn("fallback", names)

    def test_rwkv7_adapter_execution_path_matches_public_runtime_contract(self):
        import importlib.util
        import sys
        import types
        from unittest.mock import patch
        import torch
        from asm.rwkv7_core import RWKV7LanguageCore
        from asm.encoder import ConceptEncoder

        class FakeRWKV:
            def __init__(self, model, strategy):
                self.model = model
                self.strategy = strategy
            def forward(self, tokens, state):
                logits = torch.tensor([0.0, 4.0, 0.5, 0.2], dtype=torch.float32)
                next_state = [torch.tensor([float(sum(tokens)), 1.0, -0.5])]
                return logits, next_state

        class FakePipeline:
            def encode(self, text):
                return [1, 2, 3]
            def decode(self, tokens):
                return "ok\n\n" if tokens else ""
            def sample_logits(self, logits, temperature=1.0, top_p=0.5):
                return 1

        fake_pkg = types.ModuleType("rwkv")
        fake_model = types.ModuleType("rwkv.model")
        fake_utils = types.ModuleType("rwkv.utils")
        fake_model.RWKV = FakeRWKV
        fake_utils.PIPELINE = lambda model, tokenizer: FakePipeline()

        with tempfile.TemporaryDirectory() as td:
            model_file = Path(td) / "fake.pth"
            model_file.write_bytes(b"fake")
            old = {k: sys.modules.get(k) for k in ("rwkv", "rwkv.model", "rwkv.utils")}
            try:
                sys.modules["rwkv"] = fake_pkg
                sys.modules["rwkv.model"] = fake_model
                sys.modules["rwkv.utils"] = fake_utils
                with patch.object(importlib.util, "find_spec", return_value=object()):
                    core = RWKV7LanguageCore(
                        ConceptEncoder(),
                        model_path=model_file,
                        strategy="cpu fp32",
                        embedding_dims=16,
                        max_new_tokens=4,
                    )
                    self.assertTrue(core.health()["ready"])
                    read = core.read("hello")
                    self.assertEqual(read.backend, "rwkv7")
                    self.assertEqual(len(read.embedding), 16)
                    self.assertTrue(any(abs(x) > 0 for x in read.embedding))
                    generated = core.generate({"attention": {}, "internal": {}}, instruction="reply")
                    self.assertEqual(generated.backend, "rwkv7")
                    self.assertEqual(generated.text, "ok")
            finally:
                for key, value in old.items():
                    if value is None:
                        sys.modules.pop(key, None)
                    else:
                        sys.modules[key] = value


if __name__ == "__main__":
    unittest.main()
