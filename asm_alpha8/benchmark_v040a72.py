from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path
from asm.engine import ASMEngine


def trust(e, source='oracle'):
    for i in range(80):
        e.observe_evidence_source(source, observation='A', resolved_hypothesis='A', temporal_index=i)


def observe(e, tag, xs, fn, *, auto, mechanism='f', root=None):
    out=[]
    for x in xs:
        kw={}
        if root is not None: kw['root_id']=root
        out.append(e.observe_procedure(
            mechanism, {'x':x}, fn(x), evidence_id=f'{tag}-{x}', source_id='oracle',
            auto_induce=auto, **kw
        ))
    return out


def active_accuracy(e, fn, mechanism='f'):
    correct=predicted=0
    for x in range(-100,101):
        r=e.predict_procedure(mechanism, {'x':x})
        if r['status']=='predicted':
            predicted+=1
            correct += int(r['value']==fn(x))
    return {'predicted':predicted,'correct':correct,'accuracy':(correct/predicted if predicted else None)}


def case_discovery(auto):
    with tempfile.TemporaryDirectory() as d:
        e=ASMEngine(Path(d)/'state.db');trust(e)
        t=time.perf_counter()
        rows=observe(e,'fit',range(3),lambda x:2*x+3,auto=auto)
        after_fit=e.predict_procedure('f',{'x':99})
        observe(e,'val',range(10,18),lambda x:2*x+3,auto=auto)
        pred=e.predict_procedure('f',{'x':99});elapsed=time.perf_counter()-t
        result={'after_fit':after_fit,'final':pred,'versions':e.procedure_versions('f'),
                'accuracy':active_accuracy(e,lambda x:2*x+3),'elapsed_s':elapsed,
                'auto_last':rows[-1].get('auto_induction')}
        e.close();return result


def establish(e, auto):
    observe(e,'a-fit',range(3),lambda x:2*x+3,auto=auto)
    if not auto:e.induce_procedure('f')
    observe(e,'a-val',range(10,18),lambda x:2*x+3,auto=auto)


def case_drift(auto):
    with tempfile.TemporaryDirectory() as d:
        e=ASMEngine(Path(d)/'state.db');trust(e);establish(e,auto)
        rows=observe(e,'b-fit',range(20,23),lambda x:-3*x+7,auto=auto)
        after_three=e.predict_procedure('f',{'x':40})
        observe(e,'b-val',range(30,38),lambda x:-3*x+7,auto=auto)
        final=e.predict_procedure('f',{'x':40})
        result={'after_three':after_three,'final':final,'versions':e.procedure_versions('f'),
                'accuracy':active_accuracy(e,lambda x:-3*x+7),
                'auto_last':rows[-1].get('auto_induction')}
        e.close();return result


def case_reversal(auto):
    with tempfile.TemporaryDirectory() as d:
        e=ASMEngine(Path(d)/'state.db');trust(e);establish(e,auto)
        observe(e,'b-fit',range(20,23),lambda x:-3*x+7,auto=auto)
        if not auto:
            # BEFORE receives no manual repair call: this is the autonomy benchmark.
            pass
        else:
            observe(e,'b-val',range(30,38),lambda x:-3*x+7,auto=True)
            rows=observe(e,'c-fit',range(40,43),lambda x:2*x+3,auto=True)
            observe(e,'c-val',range(50,58),lambda x:2*x+3,auto=True)
        final=e.predict_procedure('f',{'x':60})
        versions=e.procedure_versions('f')
        result={'final':final,'versions':versions,'accuracy':active_accuracy(e,lambda x:2*x+3)}
        if auto:result['reversal_mode']=rows[-1]['auto_induction'].get('mode')
        e.close();return result


def safety_cases():
    out={}
    with tempfile.TemporaryDirectory() as d:
        e=ASMEngine(Path(d)/'state.db');trust(e)
        rows=observe(e,'copy',range(32),lambda x:x+1,auto=True,root='same-root')
        out['same_root']={'versions':len(e.procedure_versions('f')),'last':rows[-1]['auto_induction']}
        e.close()
    with tempfile.TemporaryDirectory() as d:
        e=ASMEngine(Path(d)/'state.db')
        rows=[]
        for x in range(32):
            rows.append(e.observe_procedure('f',{'x':x},x+1,evidence_id=f'low-{x}',source_id='weak',auto_induce=True))
        out['low_trust']={'versions':len(e.procedure_versions('f')),'last':rows[-1]['auto_induction']}
        e.close()
    return out


def explicit_equivalence():
    with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
        before=ASMEngine(Path(d1)/'s.db');after=ASMEngine(Path(d2)/'s.db');trust(before);trust(after)
        observe(before,'fit',range(3),lambda x:5*x-4,auto=False);before.induce_procedure('f')
        observe(before,'val',range(10,18),lambda x:5*x-4,auto=False)
        observe(after,'fit',range(3),lambda x:5*x-4,auto=True)
        observe(after,'val',range(10,18),lambda x:5*x-4,auto=True)
        a=active_accuracy(before,lambda x:5*x-4);b=active_accuracy(after,lambda x:5*x-4)
        before.close();after.close();return {'manual_before':a,'autonomous_after':b}


def main():
    before_discovery=case_discovery(False);after_discovery=case_discovery(True)
    before_drift=case_drift(False);after_drift=case_drift(True)
    before_reversal=case_reversal(False);after_reversal=case_reversal(True)
    safety=safety_cases();equiv=explicit_equivalence()
    checks={
        'autonomous_discovery': before_discovery['final']['status']=='abstained' and after_discovery['final'].get('value')==201,
        'heldout_gate': after_discovery['after_fit']['status']=='abstained',
        'autonomous_drift_revision': before_drift['final']['status']=='abstained' and after_drift['final'].get('value')==-113,
        'full_reversal_revalidation': after_reversal['final'].get('value')==123 and after_reversal.get('reversal_mode')=='revalidation',
        'same_root_no_false_induction': safety['same_root']['versions']==0 and safety['same_root']['last'].get('trusted_independent_roots')==1,
        'low_trust_no_false_induction': safety['low_trust']['versions']==0 and safety['low_trust']['last'].get('trusted_independent_roots')==0,
        'manual_accuracy_preserved': equiv['manual_before']['accuracy']==1.0 and equiv['autonomous_after']['accuracy']==1.0,
        'unseen_coverage_preserved': equiv['manual_before']['predicted']==201 and equiv['autonomous_after']['predicted']==201,
    }
    report={'benchmark':'ASM v0.4.0-alpha.7.2 autonomous procedure induction candidate',
            'before_definition':'procedure graft with identical evidence but auto_induce disabled and no manual repair/discovery call where autonomy is under test',
            'after_definition':'same core/evidence with auto_induce enabled; held-out validation unchanged',
            'before':{'discovery':before_discovery,'drift':before_drift,'reversal':before_reversal},
            'after':{'discovery':after_discovery,'drift':after_drift,'reversal':after_reversal},
            'safety':safety,'equivalence':equiv,'checks':checks,
            'passed':sum(checks.values()),'total':len(checks)}
    Path('ALPHA72_BEFORE_AFTER.json').write_text(json.dumps(report,indent=2,sort_keys=True))
    print(json.dumps(report,indent=2,sort_keys=True))
    raise SystemExit(0 if all(checks.values()) else 1)

if __name__=='__main__':main()
