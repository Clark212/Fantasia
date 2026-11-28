import math
import tempfile
import unittest
from pathlib import Path

from asm import ASMConfig, ASMEngine
from asm.language_core import LanguageProposal, validate_language_proposal
from asm.rwkv7_core import RWKV7LanguageCore
from asm.semantic import OnlineSemanticMap


class Alpha52ArchitectureTests(unittest.TestCase):
    def test_semantic_sparse_accumulator_matches_direct_cosine(self):
        sem = OnlineSemanticMap(similarity_threshold=0.0, min_observations=1, max_aliases=20)
        streams = [
            ["alpha", "beta", "gamma", "delta"],
            ["alpha", "beta", "theta"],
            ["beta", "gamma", "theta"],
            ["alpha", "delta", "theta"],
        ] * 3
        for row in streams:
            sem.observe(row)
        term = "alpha"
        got = dict(sem.similar(term))
        view = sem._view(term)
        direct = {}
        candidates = set()
        for ctx in view:
            bucket = sem.reverse.get(ctx, ())
            if len(bucket) <= sem.max_context_reverse:
                candidates.update(bucket)
        candidates.discard(term)
        ranked = []
        for other in candidates:
            if sem.usage.get(other, 0) < sem.min_observations:
                continue
            ov = sem._view(other)
            shared = len(set(view) & set(ov))
            if shared:
                ranked.append((other, shared, ov))
        ranked.sort(key=lambda x: x[1], reverse=True)
        for other, _, ov in ranked[:sem.max_candidates]:
            score = sem._cosine(view, ov)
            if score >= sem.threshold:
                direct[other] = score
        for key in direct:
            self.assertAlmostEqual(got[key], direct[key], places=12)

    def test_language_proposal_firewall_rejects_bad_values(self):
        bad = LanguageProposal("belief", {"holder": "mina", "proposition_text": "gate open"}, float("nan"))
        ok, reason = validate_language_proposal(bad)
        self.assertFalse(ok)
        self.assertEqual(reason, "confidence_range")
        good = LanguageProposal("belief", {"holder": "mina", "proposition_text": "gate open", "polarity": True}, 0.88)
        self.assertEqual(validate_language_proposal(good), (True, None))

    def test_rwkv_constrained_parser_accepts_only_valid_schema(self):
        raw = '<json>{"proposals":[{"kind":"belief","payload":{"holder":"mina","proposition_text":"gate open","polarity":true},"confidence":0.91},{"kind":"drive","payload":{"holder":"mina","kind":"INVALID","proposition_text":"leave","priority":0.5},"confidence":0.9}]}</json>'
        proposals = RWKV7LanguageCore._proposals_from_extractor_output(raw)
        self.assertEqual(len(proposals), 1)
        self.assertEqual(proposals[0].kind, "belief")

    def test_generation_context_contains_beliefs_goals_world_and_memory_slots(self):
        core = object.__new__(RWKV7LanguageCore)
        state = {
            "attention": {"epicenter": "WORD:gate"},
            "internal": {"confidence": 0.7},
            "beliefs": {"strategy": {"truth": True}},
            "agent_beliefs": [{"holder": "mina", "proposition": "gate open", "truth": True}],
            "goals": [{"text": "reach gate", "priority": 0.8}],
            "world_states": [{"proposition_surface": "gate open", "truth": True}],
            "relevant_memories": [{"event_id": 2, "text": "Mina opened the gate", "relevance": 0.9}],
            "workspace": [["WORD:gate", 1.0]],
        }
        prompt = core._state_prompt(state, "Explain the gate state")
        for needle in ("agent_beliefs", "goals", "world_states", "relevant_memories", "ASM_CONTEXT_JSON"):
            self.assertIn(needle, prompt)

    def test_engine_rejects_invalid_external_proposal_before_persistence(self):
        from asm.language_core import CallableLanguageCore, LanguageReadResult, LanguageGenerationResult
        def reader(text):
            return LanguageReadResult(text=text, backend="fake", tokens=[], embedding=[0.0]*96, proposals=[
                LanguageProposal("belief", {"holder":"mina", "proposition_text":"gate open"}, float("inf"), source="fake")
            ])
        def writer(state, instruction):
            return LanguageGenerationResult("", "fake")
        core = CallableLanguageCore(reader, writer, name="fake")
        with tempfile.TemporaryDirectory() as td:
            e = ASMEngine(Path(td)/"x.db", config=ASMConfig(snapshot_every_events=999999), language_core=core)
            result = e.process("neutral input", training=False)
            rejected = result["language_core"]["rejected"]
            self.assertTrue(any(str(x.get("reason", "")).startswith("proposal_contract:") for x in rejected))
            self.assertEqual(e.minds.states, {})
            e.close()


if __name__ == "__main__":
    unittest.main()
