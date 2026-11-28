import hashlib, io, unittest
from array import array
import torch
from asm import __version__
from asm.transition_mechanism import LocalRecurrentTransitionMechanism

class Alpha9MultiChoiceConsolidationTests(unittest.TestCase):
    def build(self, **kw):
        opts=dict(hidden_dim=16, train_steps=1, max_outcomes=8, outcome_capacity_limit=64,
                  retention_anchor_limit=4, retention_anchor_batch_limit=2,
                  consolidation_table_size=128, consolidation_hashes=3,
                  consolidation_min_support=2, consolidation_max_displacements=16)
        opts.update(kw)
        m=LocalRecurrentTransitionMechanism('a9_unit', **opts); m.replay_limit=4; return m

    def test_version(self):
        self.assertEqual(__version__, '0.4.0-alpha.7.9')

    def test_one_copy_layout_uses_one_cell_per_mapping_without_pressure(self):
        m=self.build(); m.total_observations=1000
        m.outcome_to_slot={str(i):i for i in range(40)};m.slot_to_outcome={i:{'r':i} for i in range(40)}
        for i in range(40):
            sig=m._input_signature({'k':i},'go',None,1.0); fp=m._consolidation_fingerprint(sig)
            for _ in range(3): m._place_consolidation_record(fp,i,1)
        st=m.stats()
        self.assertEqual(st['consolidation_used_cells'],40)
        self.assertEqual(st['consolidation_layout_version'],3)
        self.assertEqual(st['consolidation_bytes'],128*3*(8+4+2))

    def test_collisions_relocate_without_wrong_recall(self):
        m=self.build(consolidation_table_size=64);m.total_observations=1000
        n=120;m.outcome_to_slot={str(i):i for i in range(n)};m.slot_to_outcome={i:{'r':i} for i in range(n)}
        sigs=[]
        for i in range(n):
            sig=m._input_signature({'k':i,'b':i%7},'go',None,1.0);sigs.append(sig)
            fp=m._consolidation_fingerprint(sig)
            for _ in range(3):m._place_consolidation_record(fp,i,1)
        wrong=0;ok=0
        for i,sig in enumerate(sigs):
            slot,_,_=m._query_consolidation(sig)
            ok += int(slot==i); wrong += int(slot is not None and slot!=i)
        self.assertEqual(wrong,0)
        self.assertGreaterEqual(ok,115)
        self.assertGreater(m.stats()['consolidation_displacements'],0)

    def test_serialization_preserves_layout(self):
        m=self.build();
        for i in range(12):
            for r in range(3):m.observe(entity_id=f'{i}_{r}',state={'k':i},action='go',after_state={'r':i})
        blob=m.export_blob();r=self.build();r.import_blob(blob)
        self.assertEqual(r.stats()['consolidation_layout_version'],3)
        self.assertEqual(r.stats()['consolidation_used_cells'],m.stats()['consolidation_used_cells'])
        self.assertEqual(r.stats()['consolidation_bytes'],m.stats()['consolidation_bytes'])

    def test_alpha8_legacy_duplicate_layout_migrates(self):
        m=self.build(); payload=torch.load(io.BytesIO(m.export_blob()),map_location='cpu',weights_only=False)
        cells=128*3;fps=array('Q',[0])*cells;slots=array('i',[-1])*cells;sup=array('H',[0])*cells
        signatures=[]
        payload['outcome_to_slot']={str({'r':i}):i for i in range(6)}
        payload['slot_to_outcome']={i:{'r':i} for i in range(6)}
        payload['total_observations']=1000;payload['retention_anchor_limit']=1
        for i in range(6):
            sig=m._input_signature({'k':i},'go',None,1.0);signatures.append(sig)
            fp=m._consolidation_fingerprint(sig)
            for t in range(3):
                raw=hashlib.sha256(f'a8|{t}|{sig}'.encode()).digest();idx=t*128+int.from_bytes(raw[:8],'big')%128
                fps[idx]=fp;slots[idx]=i;sup[idx]=4
        payload.pop('consolidation_layout_version',None);payload['consolidation_fingerprints']=fps.tobytes();payload['consolidation_slots']=slots.tobytes();payload['consolidation_support']=sup.tobytes()
        out=io.BytesIO();torch.save(payload,out)
        r=self.build();r.import_blob(out.getvalue());r.retention_anchor_limit=1;r.total_observations=1000
        self.assertEqual(r.stats()['consolidation_layout_version'],3)
        for i,sig in enumerate(signatures):
            self.assertEqual(r._query_consolidation(sig)[0],i)

if __name__=='__main__':unittest.main()
