import io
import unittest
from array import array
import torch
from asm import __version__
from asm.transition_mechanism import LocalRecurrentTransitionMechanism

class Alpha10PackedConsolidationTests(unittest.TestCase):
    def build(self, **kw):
        opts=dict(hidden_dim=12, train_steps=1, max_outcomes=8, outcome_capacity_limit=4096,
                  retention_anchor_limit=4, retention_anchor_batch_limit=2,
                  consolidation_table_size=128, consolidation_hashes=3,
                  consolidation_min_support=2, consolidation_max_displacements=24)
        opts.update(kw)
        m=LocalRecurrentTransitionMechanism('a10_unit', **opts); m.replay_limit=4; return m

    def test_version(self):
        self.assertEqual(__version__, '0.4.0-alpha.7.9')

    def test_same_budget_yields_more_cells(self):
        m=self.build(); st=m.stats()
        self.assertEqual(st['consolidation_layout_version'],3)
        self.assertEqual(st['consolidation_bytes'],128*3*14)
        self.assertEqual(st['consolidation_cells'],(128*3*14)//12)
        self.assertGreater(st['consolidation_cells'],128*3)

    def test_meta_pack_round_trip(self):
        m=self.build()
        for slot,support in [(0,1),(7,4),(1023,99),(4095,4095)]:
            meta=m._pack_consolidation_meta(slot,support)
            self.assertEqual(m._unpack_consolidation_meta(meta),(slot,support))

    def test_high_load_exact_recall_at_same_budget(self):
        m=self.build(consolidation_table_size=256,consolidation_max_displacements=48);m.total_observations=10000
        n=700;m.outcome_to_slot={str(i):i for i in range(n)};m.slot_to_outcome={i:{'r':i} for i in range(n)}
        sigs=[]
        for i in range(n):
            sig=m._input_signature({'kind':'p','i':i,'b':i%17},'go',None,1.0);sigs.append(sig)
            fp=m._consolidation_fingerprint(sig)
            for _ in range(3):m._place_consolidation_record(fp,i,1)
        ok=wrong=0
        for i,sig in enumerate(sigs):
            slot,_,_=m._query_consolidation(sig);ok+=int(slot==i);wrong+=int(slot is not None and slot!=i)
        self.assertEqual(wrong,0)
        self.assertGreaterEqual(ok,690)

    def test_layout3_serialization(self):
        m=self.build();m.retention_anchor_limit=1
        for i in range(10):
            for r in range(3):m.observe(entity_id=f'{i}_{r}',state={'k':i},action='go',after_state={'r':i})
        r=self.build();r.import_blob(m.export_blob());r.retention_anchor_limit=1
        self.assertEqual(r.stats()['consolidation_layout_version'],3)
        self.assertEqual(r.stats()['consolidation_bytes'],m.stats()['consolidation_bytes'])
        for i in range(10):self.assertEqual(r.predict(entity_id='x',state={'k':i},action='go').predicted_state,{'r':i})

    def test_alpha9_layout2_migrates_to_packed_layout(self):
        m=self.build();payload=torch.load(io.BytesIO(m.export_blob()),map_location='cpu',weights_only=False)
        old_cells=128*3;fps=array('Q',[0])*old_cells;slots=array('i',[-1])*old_cells;sup=array('H',[0])*old_cells
        signatures=[]
        payload['outcome_to_slot']={str(i):i for i in range(8)};payload['slot_to_outcome']={i:{'r':i} for i in range(8)}
        payload['total_observations']=1000;payload['retention_anchor_limit']=1
        # Physical location does not matter to migration; it enumerates alpha.9 cells then re-places records.
        for i in range(8):
            sig=m._input_signature({'k':i},'go',None,1.0);signatures.append(sig);fps[i]=m._consolidation_fingerprint(sig);slots[i]=i;sup[i]=4
        payload['consolidation_layout_version']=2
        payload.pop('consolidation_meta',None);payload.pop('consolidation_byte_budget',None)
        payload['consolidation_fingerprints']=fps.tobytes();payload['consolidation_slots']=slots.tobytes();payload['consolidation_support']=sup.tobytes()
        out=io.BytesIO();torch.save(payload,out)
        r=self.build();r.import_blob(out.getvalue());r.retention_anchor_limit=1;r.total_observations=1000
        self.assertEqual(r.stats()['consolidation_layout_version'],3)
        for i,sig in enumerate(signatures):self.assertEqual(r._query_consolidation(sig)[0],i)

if __name__=='__main__':unittest.main()
