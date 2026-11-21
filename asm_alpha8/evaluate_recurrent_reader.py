from __future__ import annotations
import importlib.util
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
exec((ROOT/'train_recurrent_reader.py').read_text(encoding='utf-8').split('holder = _CharGRUModel',1)[0])

from asm.recurrent_reader import FrozenRecurrentLanguageCore
from asm.encoder import ConceptEncoder

core=FrozenRecurrentLanguageCore(
    ConceptEncoder(),
    model_path=ROOT/'asm/data/recurrent_reader_v020a2.pt',
    metadata_path=ROOT/'asm/data/recurrent_reader_v020a2.json',
    min_intent_confidence=0.0,
)
rows=val_rows
correct=0
stats={x:[0,0] for x in [0.5,0.6,0.7,0.8,0.9]}
confusions={}
for text,label in rows:
    pred,_=core._predict(text)
    ok=pred.label==label
    correct+=ok
    confusions[(label,pred.label)]=confusions.get((label,pred.label),0)+1
    for th in stats:
        if pred.confidence>=th:
            stats[th][1]+=1
            stats[th][0]+=int(ok)
print('overall',correct/len(rows),len(rows))
for th,(good,n) in stats.items():
    print('threshold',th,'coverage',n/len(rows),'selective_accuracy',good/n if n else None,'n',n)
print('top confusions')
for (a,b),n in sorted(confusions.items(), key=lambda kv:-kv[1])[:20]:
    print(n,a,'->',b)
