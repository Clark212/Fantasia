"""Versioned external-proposal envelope. Validation does not grant authority.

Observation/action envelopes remain proposals. Only externally resolved core
APIs may train procedures or source reliability; a backend cannot self-label.
"""
import copy
import math
from .evidence_lineage import bounded_id
from .procedure_program import Program

KINDS={'entity','relation','proposition','observation','requested_action','candidate_procedure'}


def probability(x):
    return type(x) in (int,float) and 0<=x<=1 and math.isfinite(x)


def scalar(x):
    return x is None or type(x) is bool or type(x) in (int,float) and abs(x)<=10**12 and math.isfinite(x) or isinstance(x,str) and len(x)<=512


def exact_keys(data,required,optional=()):
    if not isinstance(data,dict) or not set(required)<=set(data) or set(data)-set(required)-set(optional):raise ValueError('proposal fields mismatch')


def identifiers(xs,maximum):
    if not isinstance(xs,list) or len(xs)>maximum:raise ValueError('identifier list out of bounds')
    for x in xs:bounded_id(x)
    if len(set(xs))!=len(xs):raise ValueError('duplicate identifier')


def validate_proposal(data):
    exact_keys(data,{'schema','kind','source','confidence','evidence','context','temporal','payload'})
    if type(data['schema']) is not int or data['schema']!=1 or not isinstance(data['kind'],str) or data['kind'] not in KINDS:raise ValueError('unsupported proposal schema/kind')
    bounded_id(data['source'],'source')
    if not probability(data['confidence']):raise ValueError('invalid confidence')
    identifiers(data['evidence'],64)
    if not isinstance(data['context'],str) or len(data['context'])>256:raise ValueError('invalid context')
    temporal=data['temporal']
    exact_keys(temporal,{'start','end','tense'})
    if not isinstance(temporal['tense'],str) or temporal['tense'] not in ('past','present','future','unspecified'):raise ValueError('invalid tense')
    for k in ('start','end'):
        x=temporal[k]
        if x is not None and (type(x) not in (int,float) or not math.isfinite(x)):raise ValueError('invalid time')
    if temporal['start'] is not None and temporal['end'] is not None and temporal['end']<temporal['start']:raise ValueError('reversed time interval')
    p=data['payload'];kind=data['kind']
    if kind=='entity':
        exact_keys(p,{'id','type','attributes'});bounded_id(p['id']);bounded_id(p['type'])
        if not isinstance(p['attributes'],dict) or len(p['attributes'])>16:raise ValueError('invalid attributes')
        for k,v in p['attributes'].items():
            bounded_id(k)
            if not scalar(v):raise ValueError('invalid attribute value')
    elif kind in ('relation','proposition'):
        fields={'subject','predicate','object','negated'}
        if kind=='proposition':fields|={'belief_owner','belief_path','uncertainty'}
        exact_keys(p,fields)
        bounded_id(p['subject']);bounded_id(p['predicate'])
        if not scalar(p['object']) or type(p['negated']) is not bool:raise ValueError('invalid relation/negation')
        if kind=='proposition':
            bounded_id(p['belief_owner']);identifiers(p['belief_path'],3)
            if p['belief_path'] and p['belief_path'][0]!=p['belief_owner']:raise ValueError('belief path owner mismatch')
            if not probability(p['uncertainty']):raise ValueError('invalid uncertainty')
    elif kind=='observation':
        exact_keys(p,{'evidence_id','variable','value','parents'})
        bounded_id(p['evidence_id']);bounded_id(p['variable']);identifiers(p['parents'],32)
        if not scalar(p['value']):raise ValueError('invalid observation value')
    elif kind=='requested_action':
        exact_keys(p,{'name','arguments'});bounded_id(p['name'])
        if not isinstance(p['arguments'],dict) or len(p['arguments'])>16:raise ValueError('invalid action arguments')
        for k,v in p['arguments'].items():
            bounded_id(k)
            if not scalar(v):raise ValueError('invalid action argument')
    elif kind=='candidate_procedure':
        exact_keys(p,{'mechanism','program','training_ids'});bounded_id(p['mechanism']);identifiers(p['training_ids'],64)
        Program.from_dict(p['program'])
    return copy.deepcopy(data)
