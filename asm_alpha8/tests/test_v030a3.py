import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path

from asm import __version__
from asm.transition_mechanism import TransitionMechanismBank

DOOR = [
    ({"kind":"door","mode":"closed"}, "open", {"kind":"door","mode":"open"}),
    ({"kind":"door","mode":"open"}, "close", {"kind":"door","mode":"closed"}),
    ({"kind":"door","mode":"closed"}, "lock", {"kind":"door","mode":"locked"}),
    ({"kind":"door","mode":"locked"}, "unlock", {"kind":"door","mode":"closed"}),
    ({"kind":"door","mode":"locked"}, "open", {"kind":"door","mode":"locked"}),
]
SWITCH = [
    ({"kind":"switch","on":False}, "toggle", {"kind":"switch","on":True}),
    ({"kind":"switch","on":True}, "toggle", {"kind":"switch","on":False}),
    ({"kind":"switch","on":False}, "set_on", {"kind":"switch","on":True}),
    ({"kind":"switch","on":True}, "set_off", {"kind":"switch","on":False}),
]
CONTAINER = [
    ({"kind":"container","open":False,"filled":False}, "open", {"kind":"container","open":True,"filled":False}),
    ({"kind":"container","open":True,"filled":False}, "close", {"kind":"container","open":False,"filled":False}),
    ({"kind":"container","open":True,"filled":False}, "insert", {"kind":"container","open":True,"filled":True}),
    ({"kind":"container","open":True,"filled":True}, "remove", {"kind":"container","open":True,"filled":False}),
    ({"kind":"container","open":False,"filled":False}, "insert", {"kind":"container","open":False,"filled":False}),
]
HISTORY_STATE={"kind":"history","signal":"neutral"}

class Alpha3MechanismTests(unittest.TestCase):
    def setUp(self):
        fd,self.path=tempfile.mkstemp(suffix='.db'); os.close(fd)
        self.bank=TransitionMechanismBank(self.path,hidden_dim=64,train_steps=4,learning_rate=.008,seed=17)
    def tearDown(self):
        try:self.bank.close()
        except Exception:pass
        for suffix in ('','-wal','-shm'):
            try:os.remove(self.path+suffix)
            except FileNotFoundError:pass

    def train_static(self,cases,prefix,epochs=4):
        for _ in range(epochs):
            for i in range(2):
                for s,a,o in cases:
                    self.bank.observe('generic_transition',entity_id=f'{prefix}{i}',state=s,action=a,after_state=o)
    def eval_static(self,cases,entity):
        return sum(self.bank.predict('generic_transition',entity_id=entity,state=s,action=a)['predicted_state']==o for s,a,o in cases)
    def train_history(self,epochs=25):
        for _ in range(epochs):
            for e,p,bit in [('hl','prime_left',0),('hr','prime_right',1)]:
                self.bank.observe('generic_transition',entity_id=e,state=HISTORY_STATE,action=p,after_state=HISTORY_STATE)
                self.bank.observe('generic_transition',entity_id=e,state=HISTORY_STATE,action='read',after_state={'kind':'history','bit':bit})

    def test_version(self):
        self.assertEqual(__version__,'0.4.0-alpha.7.9')

    def test_shared_mechanism_multidomain_retention_and_history(self):
        self.train_static(DOOR,'door'); self.train_static(SWITCH,'switch'); self.train_static(CONTAINER,'container')
        self.train_history()
        self.assertEqual(self.eval_static(DOOR,'door_new'),5)
        self.assertEqual(self.eval_static(SWITCH,'switch_new'),4)
        self.assertEqual(self.eval_static(CONTAINER,'container_new'),5)
        for e,p,bit in [('new_l','prime_left',0),('new_r','prime_right',1)]:
            self.bank.reset_context('generic_transition',e)
            self.bank.observe('generic_transition',entity_id=e,state=HISTORY_STATE,action=p,after_state=HISTORY_STATE)
            pred=self.bank.predict('generic_transition',entity_id=e,state=HISTORY_STATE,action='read')
            self.assertEqual(pred['predicted_state'],{'kind':'history','bit':bit})
        self.assertEqual(self.bank.stats()['mechanisms'],1)

    def test_balanced_replay_keeps_older_structures(self):
        # Learn one sample from three schemas, then flood a fourth schema.
        for s,a,o in (DOOR[:1]+SWITCH[:1]+CONTAINER[:1]):
            self.bank.observe('generic_transition',entity_id='seed',state=s,action=a,after_state=o)
        mech=self.bank._get('generic_transition',create=False); mech.replay_limit=16
        for i in range(30):
            bit=i%2
            self.bank.observe('generic_transition',entity_id='hist',state=HISTORY_STATE,action=f'prime_{bit}',after_state=HISTORY_STATE)
        strata={x.get('stratum') for x in mech.replay}
        self.assertGreaterEqual(len(strata),4)
        self.assertLessEqual(len(mech.replay),16)

    def test_context_trace_persists_and_resets(self):
        self.bank.observe('generic_transition',entity_id='x',state=HISTORY_STATE,action='prime_left',after_state=HISTORY_STATE)
        mech=self.bank._get('generic_transition',create=False)
        self.assertTrue(mech.context_trace.get('x'))
        self.bank.close()
        self.bank=TransitionMechanismBank(self.path,hidden_dim=64,train_steps=4,learning_rate=.008,seed=17)
        mech=self.bank._get('generic_transition',create=False)
        self.assertTrue(mech.context_trace.get('x'))
        self.bank.reset_context('generic_transition','x')
        self.assertNotIn('x',mech.context_trace)

    def test_alpha2_model_blob_upgrades(self):
        alpha2_path=Path(__file__).resolve().parents[2]/'ASM_v0.3.0-alpha.2'/'asm'/'transition_mechanism.py'
        if not alpha2_path.exists(): self.skipTest('alpha.2 source unavailable')
        spec=importlib.util.spec_from_file_location('alpha2_tm_upgrade',alpha2_path)
        mod=importlib.util.module_from_spec(spec); sys.modules[spec.name]=mod; spec.loader.exec_module(mod)
        legacy=self.path+'.legacy'; old=mod.TransitionMechanismBank(legacy,hidden_dim=32,train_steps=2,learning_rate=.01,seed=7)
        try:
            for _ in range(3):
                for s,a,o in DOOR:old.observe('door_state',entity_id='a',state=s,action=a,after_state=o)
        finally:old.close()
        upgraded=TransitionMechanismBank(legacy,hidden_dim=32,train_steps=2,learning_rate=.01,seed=7)
        try:
            mech=upgraded._get('door_state',create=False)
            self.assertTrue(all('stratum' in x and 'input_signature' in x for x in mech.replay))
            pred=upgraded.predict('door_state',entity_id='new',state=DOOR[0][0],action=DOOR[0][1])
            self.assertIsNotNone(pred['predicted_state'])
            self.assertGreater(pred['support'],0)
        finally:
            upgraded.close()
            for suffix in ('','-wal','-shm'):
                try:os.remove(legacy+suffix)
                except FileNotFoundError:pass

if __name__=='__main__':unittest.main()
