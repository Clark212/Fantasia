"""Small, explicit English relation grammar; not a general language model.

The vocabulary is hand-authored. Unknown and ambiguous constructions are kept
as diagnostics, not silently converted into asserted causal relationships.
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import List, Tuple
from .encoder import STOPWORDS, light_stem

WORDS = re.compile(r"[a-z0-9_+#'-]+")

@dataclass(slots=True)
class Relation:
    left: str
    kind: str
    right: str
    confidence: float = 1.0
    negated: bool = False

    @property
    def key(self) -> str:
        return ('NOT:' if self.negated else '') + self.kind

@dataclass(slots=True)
class StructuralFrame:
    text: str
    entities: List[str]
    relations: List[Relation]
    cues: List[str]
    warnings: List[str] = field(default_factory=list)

    def signature(self) -> Tuple[str, ...]:
        return tuple(r.key for r in self.relations)

    @property
    def supported(self) -> bool:
        return bool(self.relations) and not self.warnings and all(r.kind != 'STATE' for r in self.relations)

class StructuralParser:
    # Verb forms are deliberately explicit. No query-specific entity names.
    VERBS = {
        'CAUSE': r'causes?|caused|makes?|made|produces?|produced|creates?|created|leads? to|led to|brings? about|brought about|results? in|resulted in|gives? rise to|gave rise to',
        'INCREASE': r'increases?|increased|raises?|raised|boosts?|boosted|elevates?|elevated|amplifies|amplify|amplified|heightens?|heightened',
        'DECREASE': r'decreases?|decreased|reduces?|reduced|lowers?|lowered|diminishes|diminish|diminished|lessens?|lessened|cuts?|cut',
        'ENABLE': r'enables?|enabled|allows?|allowed|permits?|permitted|facilitates?|facilitated',
        'PREVENT': r'prevents?|prevented|blocks?|blocked|stops?|stopped|inhibits?|inhibited',
        'TRIGGER': r'triggers?|triggered|activates?|activated|initiates?|initiated|sets? off|set off',
        'BECOME': r'becomes?|became|turns? into|turned into',
    }
    PARTICIPLES = {
        'CAUSE': r'caused|made|produced|created|brought about',
        'INCREASE': r'increased|raised|boosted|elevated|amplified|heightened',
        'DECREASE': r'decreased|reduced|lowered|diminished|lessened|cut',
        'ENABLE': r'enabled|allowed|permitted|facilitated',
        'PREVENT': r'prevented|blocked|stopped|inhibited',
        'TRIGGER': r'triggered|activated|initiated|set off',
    }
    CONTRACTIONS = {"doesn't": 'does not', "don't": 'do not', "didn't": 'did not',
                    "isn't": 'is not', "aren't": 'are not', "wasn't": 'was not',
                    "weren't": 'were not', "can't": 'can not', 'cannot': 'can not',
                    "won't": 'will not', "wouldn't": 'would not', "couldn't": 'could not',
                    "shouldn't": 'should not', "hasn't": 'has not', "haven't": 'have not'}
    # CUE_MAP is installed below from the v0.1.1.3 vocabulary.
    CUE_MAP = {'repeated': 'ACCUMULATION', 'repeatedly': 'ACCUMULATION', 'accumulate': 'ACCUMULATION', 'accumulates': 'ACCUMULATION', 'buildup': 'ACCUMULATION', 'limit': 'THRESHOLD', 'threshold': 'THRESHOLD', 'overload': 'OVERLOAD', 'overloaded': 'OVERLOAD', 'fail': 'FAILURE', 'fails': 'FAILURE', 'failed': 'FAILURE', 'failure': 'FAILURE', 'shutdown': 'FAILURE', 'shuts': 'FAILURE', 'crash': 'FAILURE', 'crashes': 'FAILURE', 'error': 'ERROR', 'heat': 'HEAT', 'temperature': 'HEAT', 'pressure': 'PRESSURE', 'queue': 'QUEUE', 'memory': 'MEMORY', 'power': 'ENERGY', 'battery': 'ENERGY', 'practice': 'LEARNING', 'training': 'LEARNING', 'study': 'LEARNING', 'skill': 'LEARNING', 'knowledge': 'LEARNING', 'ability': 'LEARNING', 'strength': 'LEARNING', 'voltage': 'ELECTRICAL', 'current': 'ELECTRICAL', 'circuit': 'ELECTRICAL', 'electrical': 'ELECTRICAL', 'signal': 'ELECTRICAL'}
    ADVERBS = r'(?:gradually|steadily|significantly|directly|usually|often|always|reliably|slightly)'
    PREFIX = rf'(?:(?:do|does|did|has|have|had)\s+)?(?P<neg>not\s+|never\s+)?(?:{ADVERBS}\s+)*'

    def __init__(self):
        self.active = [(k, re.compile(rf'(?P<left>.+?)\s+{self.PREFIX}(?:{v})\s+(?P<right>.+)')) for k,v in self.VERBS.items()]
        self.passive = [(k, re.compile(rf'(?P<right>.+?)\s+(?:is|are|was|were|has been|have been)\s+(?P<neg>not\s+|never\s+)?(?:{self.ADVERBS}\s+)*(?:{v})\s+by\s+(?P<left>.+)')) for k,v in self.PARTICIPLES.items()]
        self.threshold = re.compile(rf'(?P<left>.+?)\s+{self.PREFIX}(?:crosses?|crossed|exceeds?|exceeded|reaches?|reached|passes?|passed)\s+(?:a\s+|the\s+|its\s+)?(?:limit|threshold)(?:\s*,\s*(?P<right>.+))?')

    def normalize_phrase(self, phrase: str) -> str:
        toks = [light_stem(t) for t in WORDS.findall(phrase.lower()) if t not in STOPWORDS]
        return '_'.join(toks[:8]) if toks else 'unknown'

    def parse(self, text: str) -> StructuralFrame:
        raw = ' '.join(text.lower().replace('’', "'").strip().split())
        raw = re.sub(r"\b(?:"+'|'.join(re.escape(k) for k in self.CONTRACTIONS)+r")\b", lambda m:self.CONTRACTIONS[m[0]], raw)
        relations=[]; warnings=[]
        if '?' in raw:
            warnings.append('question: provide a declarative observation')
        if re.search(r'\b(?:if|when|unless|might|may|could|would|should|can|will|perhaps|maybe)\b',raw):
            warnings.append('conditional or modal statement: scope is not supported')
        if re.search(r'\b(?:not only|not always|not usually|not often|not necessarily|not entirely|no longer|neither|nor|without|fails? to|failed to|unable to)\b',raw):
            warnings.append('complex negation: scope is not supported')
        for clause in re.split(r'[.;]+|\s+and\s+then\s+|\s+but\s+|\s+and\s+(?=(?:[\w-]+\s+){0,4}(?:does|do|did)\s+not)',raw):
            clause=clause.strip(' ,!?')
            if not clause: continue
            matches=[]
            m=self.threshold.fullmatch(clause)
            if m: matches.append(('THRESHOLD',m))
            else:
                for kind,pattern in self.passive:
                    m=pattern.fullmatch(clause)
                    if m:matches.append((kind,m))
                if not matches:
                    for kind,pattern in self.active:
                        m=pattern.fullmatch(clause)
                        if m:matches.append((kind,m))
            if len(matches)==1:
                kind,m=matches[0];left=m['left'];right=m['right'] or 'threshold event'
                # Unconsumed negation or auxiliaries mean the grammar failed to
                # resolve scope. Abstain instead of dropping these words.
                if re.search(r'\b(?:not|never|no|do|does|did|is|are|was|were|has|have|had|been)\b',left):
                    warnings.append('unresolved scope in subject')
                if re.search(r'\b(?:not|never|no)\b',right):
                    warnings.append('unresolved scope in object')
                # More than one verb in an unsplit clause needs a full parser.
                if any(re.search(rf'\s(?:{v})\s', ' '+right+' ') for v in self.VERBS.values()):
                    warnings.append('multiple relations in an unsplit clause')
                relations.append(Relation(self.normalize_phrase(left),kind,self.normalize_phrase(right),negated=bool(m['neg'])))
            else:
                warnings.append('ambiguous relation' if matches else 'unrecognized relation')
                words=WORDS.findall(clause)
                if words:relations.append(Relation(self.normalize_phrase(words[0]),'STATE',self.normalize_phrase(' '.join(words[1:])),0.0))
        entities=list(dict.fromkeys(e for r in relations for e in (r.left,r.right)))
        cues=list(dict.fromkeys(self.CUE_MAP[t] for t in WORDS.findall(raw) if t in self.CUE_MAP))
        return StructuralFrame(text,entities,relations,cues,list(dict.fromkeys(warnings)))
