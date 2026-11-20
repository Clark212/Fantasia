"""A deliberately small, typed, total-budget expression language.

No imports, loops, file/network access, Python eval, or code generation. A
compiled program is a graph of vetted Python operator closures. Its evidence
and authority are owned separately by ASM's procedure cortex.
"""
from dataclasses import dataclass,field
import hashlib
import json
import operator

LIMIT=10**12
OPS={'add':operator.add,'sub':operator.sub,'mul':operator.mul,
     'min':min,'max':max,'eq':operator.eq,'lt':operator.lt,
     'and':operator.and_,'or':operator.or_}


def bounded(value):
    if type(value) is int and abs(value)>LIMIT:raise ValueError('procedure arithmetic bound exceeded')
    return value


def freeze(node,depth=0):
    if depth>8:raise ValueError('expression depth exceeded')
    if isinstance(node,(tuple,list)):
        if len(node)>4:raise ValueError('expression arity exceeded')
        return tuple(freeze(x,depth+1) for x in node)
    return node


def infer(node,inputs,budget,depth=0):
    budget[0]+=1
    if budget[0]>31 or depth>8:raise ValueError('expression size/depth exceeded')
    if type(node) is bool:return 'bool'
    if type(node) is int:
        if abs(node)>10**6:raise ValueError('literal bound exceeded')
        return 'int'
    if isinstance(node,str) and node in inputs:return inputs[node]
    if not isinstance(node,tuple) or not node or not isinstance(node[0],str):raise ValueError('invalid expression')
    op=node[0]
    if op=='not' and len(node)==2:
        if infer(node[1],inputs,budget,depth+1)!='bool':raise ValueError('not requires bool')
        return 'bool'
    if op=='if' and len(node)==4:
        ts=[infer(x,inputs,budget,depth+1) for x in node[1:]]
        if ts[0]!='bool' or ts[1]!=ts[2]:raise ValueError('conditional type mismatch')
        return ts[1]
    if op not in OPS or len(node)!=3:raise ValueError('unsupported operation/arity')
    a=infer(node[1],inputs,budget,depth+1);b=infer(node[2],inputs,budget,depth+1)
    if op in ('and','or'):
        if a!=b or a!='bool':raise ValueError('Boolean operand required')
        return 'bool'
    if op=='eq':
        if a!=b:raise ValueError('equality type mismatch')
        return 'bool'
    if a!=b or a!='int':raise ValueError('integer operands required')
    return 'bool' if op=='lt' else 'int'


def interpret(node,values):
    if isinstance(node,str):return values[node]
    if not isinstance(node,tuple):return node
    op=node[0]
    if op=='if':return interpret(node[2] if interpret(node[1],values) else node[3],values)
    if op=='not':return not interpret(node[1],values)
    return bounded(OPS[op](interpret(node[1],values),interpret(node[2],values)))


def compile_tree(node):
    if isinstance(node,str):return lambda values:values[node]
    if not isinstance(node,tuple):return lambda values:node
    op=node[0]
    a=compile_tree(node[1])
    if op=='not':return lambda values:not a(values)
    b=compile_tree(node[2])
    if op=='if':
        c=compile_tree(node[3]);return lambda values:b(values) if a(values) else c(values)
    fn=OPS[op]
    return lambda values:bounded(fn(a(values),b(values)))


@dataclass(frozen=True)
class Program:
    inputs:tuple
    expression:object
    output_type:str=field(init=False)
    size:int=field(init=False)
    _fn:object=field(init=False,repr=False,compare=False)

    def __post_init__(self):
        inputs=dict(self.inputs) if not isinstance(self.inputs,dict) else dict(self.inputs)
        if not 1<=len(inputs)<=4 or any(not isinstance(k,str) or not k.isidentifier() or len(k)>32 or v not in ('int','bool') for k,v in inputs.items()):
            raise ValueError('invalid program inputs')
        expr=freeze(self.expression);budget=[0]
        result_type=infer(expr,inputs,budget)
        object.__setattr__(self,'inputs',tuple(sorted(inputs.items())))
        object.__setattr__(self,'expression',expr)
        object.__setattr__(self,'output_type',result_type)
        object.__setattr__(self,'size',budget[0])
        object.__setattr__(self,'_fn',None)

    def validate_inputs(self,values):
        if not isinstance(values,dict) or set(values)!=set(dict(self.inputs)):raise ValueError('input keys mismatch')
        for key,kind in self.inputs:
            x=values[key]
            if type(x) is not (int if kind=='int' else bool):raise ValueError('input type mismatch')
            if kind=='int' and abs(x)>10**6:raise ValueError('input magnitude bound exceeded')

    def run(self,values,*,compiled=False):
        self.validate_inputs(values)
        if compiled:
            if self._fn is None:
                object.__setattr__(self,'_fn',compile_tree(self.expression))
            return self._fn(values)
        return interpret(self.expression,values)

    def as_dict(self):return {'inputs':dict(self.inputs),'expression':json.loads(json.dumps(self.expression))}

    @property
    def key(self):return hashlib.sha256(json.dumps(self.as_dict(),sort_keys=True,separators=(',',':')).encode()).hexdigest()

    @classmethod
    def from_dict(cls,data):
        if not isinstance(data,dict) or set(data)!= {'inputs','expression'}:raise ValueError('invalid program schema')
        if not isinstance(data['inputs'],dict):raise ValueError('program inputs must be mapping')
        return cls(data['inputs'],data['expression'])


def anti_unify(left,right):
    """Constant-only structural generalization; tied disagreements share a slot."""
    holes={}
    def visit(a,b):
        if type(a)==type(b) and a==b:return a
        if type(a) is int and type(b) is int:
            holes.setdefault((a,b),f'${len(holes)}');return holes[(a,b)]
        if isinstance(a,tuple) and isinstance(b,tuple) and len(a)==len(b) and a[0]==b[0]:
            return (a[0],)+tuple(visit(x,y) for x,y in zip(a[1:],b[1:]))
        raise ValueError('incompatible shape')
    try:tree=visit(left,right)
    except ValueError:return None
    return (tree,len(holes)) if 1<=len(holes)<=2 else None


def substitute(tree,bindings):
    if isinstance(tree,tuple):return tuple(substitute(x,bindings) for x in tree)
    return bindings.get(tree,tree) if isinstance(tree,str) else tree


def choose_experiment(programs,inputs,*,strategy='disagreement'):
    """Finite-pool, equal-prior queries. An evaluator is NEVER called here."""
    import math
    from collections import Counter
    if strategy not in ('disagreement','uncertainty'):raise ValueError('unknown strategy')
    if not 2<=len(programs)<=256 or not 1<=len(inputs)<=256:raise ValueError('query budget exceeded')
    best=None
    for values in inputs:
        try:votes=Counter(p.run(values) for p in programs)
        except (ValueError,OverflowError):continue
        n=len(programs)
        score=(-sum((v/n)*math.log2(v/n) for v in votes.values()) if strategy=='disagreement' else 1-max(votes.values())/n)
        if best is None or score>best['score']:
            best={'input':dict(values),'score':score,'distinct_predictions':len(votes)}
    return best if best is not None and best['score']>0 else None
