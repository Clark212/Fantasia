from __future__ import annotations

import json
import random
import tempfile
import unittest
from pathlib import Path

from asm.engine import ASMEngine
from asm.evidence_lineage import EvidenceLedger
from asm.procedure_cortex import ProcedureCortex
from asm.procedure_program import Program, anti_unify, choose_experiment
from asm.proposal_contract import validate_proposal
from asm.semantic import OnlineSemanticMap


class TypedProgramTests(unittest.TestCase):
    def test_compiled_interpreted_equivalence_and_fail_closed(self):
        p = Program({'x': 'int'}, ('if', ('lt', 'x', 3), ('mul', 2, 'x'), ('add', ('mul', 'x', 'x'), 1)))
        for x in range(-50, 51):
            self.assertEqual(p.run({'x': x}), p.run({'x': x}, compiled=True))
        for bad in [('exec', 'x'), ('add', True, 'x'), ('add', 'unknown', 1)]:
            with self.assertRaises(ValueError):
                Program({'x': 'int'}, bad)

    def test_family_and_disagreement_helpers(self):
        a = ('add', ('mul', 2, 'x'), 3)
        b = ('add', ('mul', 2, 'x'), 8)
        self.assertEqual(anti_unify(a, b), (('add', ('mul', 2, 'x'), '$0'), 1))
        ps = [Program({'x': 'int'}, ('mul', k, 'x')) for k in range(5)]
        self.assertEqual(choose_experiment(ps, [{'x': 0}, {'x': 3}])['input'], {'x': 3})


class AuditedProcedureTests(unittest.TestCase):
    # These lifecycle tests probe a validated affine rule at x=100, i.e. far outside the evidence range [0, 17]. Since DEV3.3 the default
    # guard abstains there, so they run in the explicit legacy mode ('off'); default-mode behaviour of the same scenario is covered in
    # test_alpha8_dev3_3_default_abstain.py. Assertions are unchanged.
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.trust = {'reliability': .99, 'version': 1}
        self.db = Path(self.tmp.name) / 'procedure.db'
        self.c = ProcedureCortex(self.db, trust_provider=lambda source: self.trust.copy(), extrapolation_guard='off')

    def tearDown(self):
        self.c.close()
        self.tmp.cleanup()

    def observe(self, mechanism, x, y, evidence_id):
        return self.c.observe(mechanism, {'x': x}, y, evidence_id=evidence_id, source_id='oracle')

    def train_affine(self, mechanism='f', a=2, b=3):
        for x in range(3):
            self.observe(mechanism, x, a * x + b, f'{mechanism}-fit-{x}')
        proposed = self.c.induce(mechanism)
        self.assertEqual(proposed['status'], 'proposed')
        self.assertEqual(self.c.predict(mechanism, {'x': 8})['status'], 'abstained')
        for x in range(10, 18):
            self.observe(mechanism, x, a * x + b, f'{mechanism}-val-{x}')
        return proposed

    def test_heldout_validation_persistence_and_suspension(self):
        self.train_affine()
        self.assertEqual(self.c.predict('f', {'x': 100})['value'], 203)
        before = self.c.versions('f')
        self.c.close()
        self.c = ProcedureCortex(self.db, trust_provider=lambda source: self.trust.copy(), extrapolation_guard='off')
        self.assertEqual(before, self.c.versions('f'))
        self.assertEqual(self.c.predict('f', {'x': 7})['value'], 17)
        self.observe('f', 100, 999, 'bad-1')
        self.assertEqual(self.c.predict('f', {'x': 7})['status'], 'abstained')

    def test_family_transfer_reduces_search_work(self):
        self.train_affine('first', 2, 3)
        self.train_affine('second', 2, 5)
        for x in range(3):
            self.observe('target', x, 2 * x + 8, f'target-{x}')
        no_family = self.c.induce('target', use_families=False)
        with_family = self.c.induce('target', use_families=True)
        self.assertEqual(no_family['program'], with_family['program'])
        self.assertLess(with_family['evaluator_calls'], no_family['evaluator_calls'])


class EvidenceAndEngineIntegrationTests(unittest.TestCase):
    def test_explicit_ledger_is_additive_to_hidden_dependency_learning(self):
        ledger = EvidenceLedger({'A': .5, 'B': .5})
        ledger.add('root', source_id='camera')
        for i in range(9):
            ledger.add(f'copy-{i}', source_id='camera', parents=['root'], likelihoods={'A': .7, 'B': .3})
        self.assertAlmostEqual(ledger.belief.as_dict()['A'], .7)
        self.assertEqual(ledger.suppressed, 8)
        restored = EvidenceLedger.from_state(json.loads(json.dumps(ledger.export_state())))
        self.assertEqual(restored.belief.as_dict(), ledger.belief.as_dict())

    def test_engine_procedure_binds_to_alpha71_source_regime(self):
        with tempfile.TemporaryDirectory() as d:
            engine = ASMEngine(Path(d) / 'state.db')
            try:
                for i in range(80):
                    engine.observe_evidence_source('oracle', observation='A', resolved_hypothesis='A', temporal_index=i)
                self.assertGreater(engine._procedure_trust_status('oracle')['reliability'], .8)
                for x in range(3):
                    engine.observe_procedure('f', {'x': x}, 2*x+3, evidence_id=f'fit-{x}', source_id='oracle')
                engine.induce_procedure('f')
                for x in range(10, 18):
                    engine.observe_procedure('f', {'x': x}, 2*x+3, evidence_id=f'val-{x}', source_id='oracle')
                self.assertEqual(engine.predict_procedure('f', {'x': 5})['value'], 13)
                # Force a genuine source reliability regime change. The old procedure must abstain.
                changed = False
                for t in range(80, 180):
                    row = engine.observe_evidence_source('oracle', observation='B', resolved_hypothesis='A', temporal_index=t)
                    if row['regime_changed']:
                        changed = True
                        break
                self.assertTrue(changed)
                result = engine.predict_procedure('f', {'x': 5})
                self.assertEqual(result['status'], 'abstained')
                self.assertEqual(result['reason'], 'dependency_invalidated')
            finally:
                engine.close()

    def test_structured_proposals_never_execute_actions(self):
        action = {
            'schema': 1, 'kind': 'requested_action', 'source': 'backend', 'confidence': .9,
            'evidence': [], 'context': '',
            'temporal': {'start': None, 'end': None, 'tense': 'present'},
            'payload': {'name': 'move', 'arguments': {'steps': 3}},
        }
        self.assertEqual(validate_proposal(action), action)
        with tempfile.TemporaryDirectory() as d:
            engine = ASMEngine(Path(d) / 'state.db')
            try:
                result = engine.submit_structured_proposal(action)
                self.assertFalse(result['executed'])
                self.assertEqual(result['status'], 'requires_grounding')
            finally:
                engine.close()

    def test_candidate_proposal_enters_gate_but_does_not_execute(self):
        with tempfile.TemporaryDirectory() as d:
            engine = ASMEngine(Path(d) / 'state.db')
            try:
                for i in range(40):
                    engine.observe_evidence_source('oracle', observation='A', resolved_hypothesis='A', temporal_index=i)
                training_ids = []
                for x in range(3):
                    eid = f'fit-{x}'
                    training_ids.append(eid)
                    engine.observe_procedure('f', {'x': x}, 2*x+3, evidence_id=eid, source_id='oracle')
                proposal = {
                    'schema': 1, 'kind': 'candidate_procedure', 'source': 'backend', 'confidence': .9,
                    'evidence': training_ids, 'context': '',
                    'temporal': {'start': None, 'end': None, 'tense': 'unspecified'},
                    'payload': {
                        'mechanism': 'f',
                        'program': Program({'x': 'int'}, ('add', ('mul', 2, 'x'), 3)).as_dict(),
                        'training_ids': training_ids,
                    },
                }
                result = engine.submit_structured_proposal(proposal)
                self.assertFalse(result['executed'])
                self.assertEqual(result['result']['status'], 'proposed')
                self.assertEqual(engine.predict_procedure('f', {'x': 9})['status'], 'abstained')
            finally:
                engine.close()

    def test_procedure_prediction_does_not_train_dependency_model(self):
        with tempfile.TemporaryDirectory() as d:
            engine = ASMEngine(Path(d) / 'state.db')
            try:
                for i in range(80):
                    engine.observe_evidence_source('oracle', observation='A', resolved_hypothesis='A', temporal_index=i)
                for x in range(3):
                    engine.observe_procedure('f', {'x': x}, x + 1, evidence_id=f'f{x}', source_id='oracle')
                engine.induce_procedure('f')
                for x in range(10, 18):
                    engine.observe_procedure('f', {'x': x}, x + 1, evidence_id=f'v{x}', source_id='oracle')
                before = engine.evidence_dependency.export_state()
                for _ in range(20):
                    engine.predict_procedure('f', {'x': 50})
                self.assertEqual(before, engine.evidence_dependency.export_state())
            finally:
                engine.close()


class SemanticOptimizationTests(unittest.TestCase):
    def test_pair_cache_exactly_matches_uncached(self):
        for seed in range(2):
            rng = random.Random(seed)
            kw = dict(max_contexts=8, max_context_reverse=16, max_candidates=12, min_observations=2)
            a = OnlineSemanticMap(**kw, pair_cache_enabled=False)
            b = OnlineSemanticMap(**kw, pair_cache_enabled=True)
            for t in range(250):
                vocab = [f'w{x}' for x in range(10 if t < 100 else 50)]
                words = rng.sample(vocab, rng.randint(1, min(8, len(vocab))))
                a.observe(words); b.observe(words)
                for w in rng.sample(vocab, min(5, len(vocab))):
                    self.assertEqual(a.similar(w), b.similar(w))
            self.assertLessEqual(len(b._pair_cosine_cache), b._pair_cache_limit)


if __name__ == '__main__':
    unittest.main()
