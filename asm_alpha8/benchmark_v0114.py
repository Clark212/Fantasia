"""Small transparent regression/coverage suite. Not a general intelligence test.

Use --project to compare the same cases against an extracted older ASM release.
"""
import argparse
import json
import platform
import random
import statistics
import sys
import tempfile
import time
from pathlib import Path
from benchmark_cases import CORE, DISTRACTORS, TESTS, PARAPHRASE_PAIRS

PASSIVE = [
 ('processor temperature is boosted by repeated computation','THRESHOLD'),
 ('pipe pressure was raised by repeated pumping','THRESHOLD'),
 ('ability is increased by practice','ENABLE'),
 ('knowledge was elevated by study','ENABLE'),
 ('voltage is raised by electrical input','TRIGGER'),
 ('circuit voltage was amplified by current','TRIGGER'),
 ('building motion is caused by ground movement','TRIGGER'),
 ('membrane motion was brought about by sound','TRIGGER'),
]
# Added after implementing the grammar. No vocabulary tuning to these results.
EXPLORATORY = [
 ('repeated compilation heightens chip temperature','THRESHOLD'),
 ('repeated heating elevates vessel pressure','THRESHOLD'),
 ('practice steadily raises dexterity','ENABLE'),
 ('study significantly boosts recall','ENABLE'),
 ('electrical input gradually amplifies voltage','TRIGGER'),
 ('signal elevates voltage','TRIGGER'),
 ('wind gives rise to panel motion','TRIGGER'),
 ('sound results in sensor motion','TRIGGER'),
 ('repeated computation drives up processor temperature','THRESHOLD'),
 ('repeated compression ramps up tank pressure','THRESHOLD'),
 ('practice enhances skill','ENABLE'),
 ('study improves knowledge','ENABLE'),
 ('electrical input pushes voltage upward','TRIGGER'),
 ('current sends circuit voltage higher','TRIGGER'),
 ('ground movement makes the building sway','TRIGGER'),
 ('air pressure gets the membrane moving','TRIGGER'),
]
NEGATIVES = [
 ('practice does not increase ability','INCREASE'),
 ("practice doesn't increase ability",'INCREASE'),
 ('practice never boosts ability','INCREASE'),
 ('training did not raise skill','INCREASE'),
 ('electrical input does not increase voltage','INCREASE'),
 ('current never raises circuit voltage','INCREASE'),
 ('wind does not cause motion','CAUSE'),
 ("sound doesn't bring about motion",'CAUSE'),
 ('vibration never produces motion','CAUSE'),
 ('voltage is not increased by current','INCREASE'),
 ('motion was not caused by wind','CAUSE'),
 ('skill was never boosted by practice','INCREASE'),
]

def evaluate(a):
 rows=[]
 groups={'original':TESTS,'familiar':[(x,k) for x,y,k in PARAPHRASE_PAIRS],
         'audit_paraphrases':[(y,k) for x,y,k in PARAPHRASE_PAIRS],
         'passive':PASSIVE,'exploratory_language':EXPLORATORY}
 for category,cases in groups.items():
  for q,expected in cases:
   t=time.perf_counter();e=a.expand_problem(q);elapsed=(time.perf_counter()-t)*1000
   if 'prediction' in e:
    prediction=e['prediction'];got=prediction['relation'];status=prediction['status']
   else:
    got=next((h['hypothesis'].split(':',1)[1] for h in e['hypotheses'] if h['hypothesis'].startswith('RELATION:')),None)
    prediction={};status='legacy_prediction' if got else 'no_prediction'
   rows.append(dict(category=category,query=q,expected=expected,predicted=got,correct=got==expected,status=status,latency_ms=elapsed,frame=e['frame'],assessment=prediction))
 for q,kind in NEGATIVES:
  e=a.expand_problem(q);r=e['frame']['relations']
  negative=bool(len(r)==1 and r[0]['kind']==kind and r[0].get('negated',False))
  predicted=e.get('prediction',{}).get('relation')
  hypothesis_predictions=[h['hypothesis'] for h in e['hypotheses'] if h['hypothesis'].startswith('RELATION:')]
  rows.append(dict(category='negation_isolation',query=q,expected='explicit negative relation and no learned continuation',correct=negative and predicted is None and not hypothesis_predictions,frame=e['frame'],assessment=e.get('prediction'),hypothesis_predictions=hypothesis_predictions))
 return rows

def summarize(rows):
 summary={}
 for c in dict.fromkeys(r['category'] for r in rows):
  subset=[r for r in rows if r['category']==c];ok=sum(r['correct'] for r in subset)
  entry={'correct':ok,'total':len(subset),'unique_questions':len({r['query'] for r in subset}),'accuracy_pct':round(100*ok/len(subset),2)}
  times=[r['latency_ms'] for r in subset if 'latency_ms' in r]
  if times:entry['median_latency_ms']=round(statistics.median(times),3)
  summary[c]=entry
 return summary

def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--project',type=Path,default=Path(__file__).resolve().parent)
 parser.add_argument('--db',type=Path)
 parser.add_argument('--seeds',type=int,default=5)
 parser.add_argument('--output',type=Path,default=Path(__file__).resolve().parent/'results'/'benchmark_v0114_summary.json')
 args=parser.parse_args()
 if args.seeds < 1:parser.error('--seeds must be positive')
 sys.path.insert(0,str(args.project.resolve()))
 from asm import ASMEngine,__version__
 import sqlite3
 result={'version':__version__,'python':platform.python_version(),'method':'Fixed synthetic training set; same test cases across versions; no test-query training. Repeated seeds are not independent questions. Audit cases are regression tests. Exploratory cases were added after implementation, but are not an independent evaluation. Scores reflect expected learned continuations, not physical certainty.','gpt_5_6_sol':'Not run; no verified endpoint available.','runs':[]}
 with tempfile.TemporaryDirectory() as td:
  for seed in range(args.seeds):
   a=ASMEngine(Path(td)/f'{seed}.db')
   try:
    train=CORE*3+DISTRACTORS*5;random.Random(seed).shuffle(train)
    for text in train:a.process(text,training=True)
    result['runs'].append({'seed':seed,'rows':evaluate(a)})
   finally:a.close()
  if args.db:
   src=sqlite3.connect(args.db.resolve().as_uri()+'?mode=ro',uri=True);dst=sqlite3.connect(Path(td)/'shipped.db')
   try:src.backup(dst)
   finally:src.close();dst.close()
   a=ASMEngine(Path(td)/'shipped.db')
   try:result['shipped_rows']=evaluate(a);result['shipped_stats']=a.stats()
   finally:a.close()
 result['summary']=summarize([r for run in result['runs'] for r in run['rows']])
 if 'shipped_rows' in result:result['shipped_summary']=summarize(result['shipped_rows'])
 args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2),encoding='utf-8')
 print(json.dumps({k:v for k,v in result.items() if k not in ['runs','shipped_rows']},indent=2))

if __name__=='__main__':main()
