import re
from collections import Counter
from typing import Dict, List

from .semantic import OnlineSemanticMap

TOKEN_RE = re.compile(r"[a-zA-Z0-9_+#.\-']+")

STOPWORDS = {
    "a","an","the","is","are","was","were","be","been","being","to","of","and","or",
    "in","on","at","for","with","from","that","this","it","as","by","i","you","we",
    "they","he","she","my","your","our","their","me","us","them","do","does","did",
    "can","could","would","should","will","just","very"
}


def light_stem(token: str) -> str:
    """
    Conservative no-dependency stemmer.
    It is deliberately small: enough to collapse forms like crashed/crash,
    running/run-ish cases, servers/server, without pretending to be a full NLP
    stemmer.
    """
    if len(token) <= 3:
        return token

    original = token

    if token.endswith("ies") and len(token) > 4:
        token = token[:-3] + "y"
    elif token.endswith("ing") and len(token) > 5:
        token = token[:-3]
        # running -> run
        if len(token) >= 2 and token[-1] == token[-2]:
            token = token[:-1]
    elif token.endswith("ed") and len(token) > 4:
        token = token[:-2]
        if len(token) >= 2 and token[-1] == token[-2]:
            token = token[:-1]
    elif token.endswith("es") and len(token) > 4:
        token = token[:-2]
    elif token.endswith("s") and len(token) > 4 and not token.endswith("ss"):
        token = token[:-1]

    return token or original


class ConceptEncoder:
    """
    Lightweight structural + continuously learned semantic encoder.

    ASM v0.1.1 still avoids a mandatory pretrained model. It now emits:
      - WORD:<surface>
      - STEM:<canonical-ish morphology>
      - PAIR:<stem_a>-><stem_b>
      - learned semantic aliases from OnlineSemanticMap
      - structural concepts such as QUESTION and COMMAND
    """

    def __init__(
        self,
        semantic_similarity_threshold: float = 0.62,
        semantic_min_observations: int = 2,
        semantic_max_aliases: int = 3,
        semantic_alias_gain: float = 0.55,
    ):
        self.semantic = OnlineSemanticMap(
            similarity_threshold=semantic_similarity_threshold,
            min_observations=semantic_min_observations,
            max_aliases=semantic_max_aliases,
        )
        self.semantic_alias_gain = semantic_alias_gain

    def tokenize(self, text: str) -> List[str]:
        return [m.group(0).lower() for m in TOKEN_RE.finditer(text)]

    def content_stems(self, text: str) -> List[str]:
        return [
            light_stem(t)
            for t in self.tokenize(text)
            if t not in STOPWORDS
        ]

    def encode(self, text: str, semantic_expand: bool = True) -> Dict[str, float]:
        raw = self.tokenize(text)
        if not raw:
            return {"EVENT:EMPTY": 1.0}

        counts = Counter(raw)
        concepts: Dict[str, float] = {}

        for token, count in counts.items():
            base = 0.30 if token in STOPWORDS else 0.92
            concepts[f"WORD:{token}"] = min(1.5, base + 0.12 * (count - 1))

            stem = light_stem(token)
            if token not in STOPWORDS:
                concepts[f"STEM:{stem}"] = max(
                    concepts.get(f"STEM:{stem}", 0.0),
                    1.0,
                )

            if token.isdigit():
                concepts["TYPE:NUMBER"] = 0.8
            if any(ch.isdigit() for ch in token) and any(ch.isalpha() for ch in token):
                concepts["TYPE:ALNUM"] = 0.7

        stems = self.content_stems(text)

        # Learned semantic expansion. No hard synonym list is used.
        if semantic_expand:
            for stem in set(stems):
                for alias, similarity in self.semantic.similar(stem):
                    key = f"STEM:{alias}"
                    concepts[key] = max(
                        concepts.get(key, 0.0),
                        self.semantic_alias_gain * similarity,
                    )
                    concepts[f"SEMREL:{stem}~{alias}"] = 0.25 * similarity

        for a, b in zip(stems, stems[1:]):
            concepts[f"PAIR:{a}->{b}"] = 0.70

        stripped = text.strip()
        if stripped.endswith("?"):
            concepts["ACT:QUESTION"] = 1.15

        first = raw[0]
        if first in {"make","build","create","run","open","stop","start","remember","learn","show","tell"}:
            concepts["ACT:COMMAND"] = 1.0

        concepts[f"LEN_BUCKET:{min(len(raw)//5, 8)}"] = 0.20
        return concepts

    def learn_semantics(self, text: str) -> None:
        stems = self.content_stems(text)
        self.semantic.observe(stems)

    def export_state(self) -> dict:
        return {"semantic": self.semantic.export_state()}

    def import_state(self, payload: dict) -> None:
        self.semantic.import_state(payload.get("semantic", {}))
