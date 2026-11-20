from __future__ import annotations

import re
from typing import Optional


class MentalLanguagePerception:
    """
    Small compositional mental-state language adapter.

    This is deliberately separate from the belief/appraisal stores.  Its job is
    to map common surface constructions into neutral events; the stores still
    own confidence revision and persistence.

    It is broader than the old exact-template regexes, but it is not a general
    English parser or pretrained language model.
    """

    # Outer predicates.  The boolean indicates whether the speaker affirms the
    # embedded mental content (True) or casts doubt on it (False).
    PREDICATES = (
        (re.compile(r"^(?:believes?|thinks?|assumes?|expects?|suspects?|figures?|reckons?)\b\s*(?:that\s+)?", re.I), True),
        (re.compile(r"^(?:is|was)\s+(?:quite\s+|pretty\s+|very\s+)?(?:sure|certain|convinced)\b\s*(?:that\s+)?", re.I), True),
        (re.compile(r"^(?:has|had)\s+(?:the\s+)?impression\b\s*(?:that\s+)?", re.I), True),
        (re.compile(r"^(?:is|was)\s+under\s+the\s+impression\b\s*(?:that\s+)?", re.I), True),
        (re.compile(r"^(?:doubts?|doubted)\b\s*(?:that\s+)?", re.I), False),
        (re.compile(r"^(?:is|was)\s+not\s+(?:sure|certain|convinced)\b\s*(?:that\s+)?", re.I), False),
    )

    ACQUISITION = (
        (re.compile(r"^(?:believes?|thinks?|assumes?|expects?|suspects?|figures?|reckons?)\b\s*(?:that\s+)?", re.I), True),
        (re.compile(r"^(?:learned|learnt|discovered|realized|realised|found\s+out|noticed|confirmed)\b\s*(?:that\s+)?", re.I), True),
        (re.compile(r"^(?:is|was)\s+(?:sure|certain|convinced)\b\s*(?:that\s+)?", re.I), True),
        (re.compile(r"^(?:doubts?|doubted)\b\s*(?:that\s+)?", re.I), False),
    )

    GOAL_PATTERNS = (
        re.compile(r"^(?:wants?|wanted|hopes?|hoped|wishes?|wished)\b\s*(?:for\s+|that\s+|to\s+)?", re.I),
        re.compile(r"^(?:had\s+been|has\s+been|was|is)\s+hoping\b\s*(?:for\s+|that\s+|to\s+)?", re.I),
        re.compile(r"^(?:desperately\s+|strongly\s+|really\s+)?(?:hopes?|hoped|wants?|wanted)\b\s*(?:for\s+|that\s+|to\s+)?", re.I),
        re.compile(r"^(?:aims?|aimed|tries?|tried)\s+to\b\s*", re.I),
    )
    FEAR_PATTERNS = (
        re.compile(r"^(?:fears?|feared)\b\s*(?:that\s+)?", re.I),
        re.compile(r"^(?:is|was|had\s+been|has\s+been)\s+(?:scared|afraid|fearful)\b\s*(?:that\s+)?", re.I),
        re.compile(r"^(?:worries?|worried)\b\s*(?:that\s+|about\s+)?", re.I),
    )
    EXPECT_PATTERNS = (
        re.compile(r"^(?:expects?|expected|predicts?|predicted|anticipates?|anticipated)\b\s*(?:that\s+)?", re.I),
    )

    SELF_FAIL = re.compile(
        r"\b(?:fail(?:ed|s|ure)?|did\s+not\s+work|didn't\s+work|was\s+wrong|broke|crashed)\b",
        re.I,
    )
    SELF_SUCCESS = re.compile(
        r"\b(?:work(?:ed|s)?(?:\s+successfully)?|succeed(?:ed|s)?|success(?:ful|fully)?|passed|solved)\b",
        re.I,
    )

    @staticmethod
    def _clean(text: str) -> str:
        return " ".join(text.strip().replace("’", "'").rstrip(".!?").split())

    @staticmethod
    def _strip_coref(prop: str, holder: str) -> str:
        prop = prop.strip(" ,")
        # For a holder-specific report, leading personal pronouns normally refer
        # back to that holder.  Removing only the leading pronoun is conservative.
        prop = re.sub(r"^(?:he|she|they|i)\s+(?:had\s+|has\s+|was\s+|is\s+)?", "", prop, flags=re.I)
        prop = re.sub(r"^the\s+", "", prop, flags=re.I)
        return prop.strip()

    @classmethod
    def _consume_predicate(cls, rest: str):
        for regex, polarity in cls.PREDICATES:
            m = regex.match(rest)
            if m:
                return rest[m.end():].strip(), polarity, m.group(0).strip()
        return None

    @classmethod
    def parse_nested(cls, text: str, max_order: int = 3) -> Optional[dict]:
        raw = cls._clean(text)
        if not raw or "?" in text:
            return None
        if re.search(r"\b(?:maybe|perhaps|might|may|could)\b", raw, re.I):
            return None

        # First holder must be sentence-initial.
        m = re.match(r"^(?P<holder>[A-Za-z][A-Za-z0-9_-]*)\s+(?P<rest>.+)$", raw)
        if not m:
            return None

        path = []
        outer_polarity = True
        holder = m.group("holder").lower()
        rest = m.group("rest").strip()

        while len(path) < max_order:
            consumed = cls._consume_predicate(rest)
            if not consumed:
                break
            rest, polarity, _ = consumed
            path.append(holder)
            outer_polarity = outer_polarity if polarity else not outer_polarity

            # A nested layer exists only if the next span starts with a named
            # holder followed by another recognized mental predicate.
            n = re.match(r"^(?P<holder>[A-Za-z][A-Za-z0-9_-]*)\s+(?P<rest>.+)$", rest)
            if not n:
                break
            candidate_holder = n.group("holder").lower()
            candidate_rest = n.group("rest").strip()
            if cls._consume_predicate(candidate_rest) is None:
                break
            holder = candidate_holder
            rest = candidate_rest

        if len(path) < 2 or not rest:
            return None

        return {
            "path": path,
            "proposition_text": rest,
            "polarity": outer_polarity,
            "confidence": 0.90 if outer_polarity else 0.80,
            "source": "mental_language",
        }

    @classmethod
    def parse_direct_belief(cls, text: str) -> Optional[dict]:
        raw = cls._clean(text)
        m = re.match(r"^(?P<holder>[A-Za-z][A-Za-z0-9_-]*)\s+(?P<rest>.+)$", raw)
        if not m:
            return None
        holder = m.group("holder").lower()
        rest = m.group("rest").strip()
        for regex, polarity in cls.ACQUISITION:
            mm = regex.match(rest)
            if not mm:
                continue
            prop = cls._strip_coref(rest[mm.end():], holder)
            if not prop:
                return None
            return {
                "holder": holder,
                "proposition_text": prop,
                "polarity": polarity,
                "confidence": 0.86 if polarity else 0.72,
                "source": "mental_language",
            }
        return None

    @classmethod
    def parse_drive(cls, text: str) -> Optional[dict]:
        raw = cls._clean(text)
        m = re.match(r"^(?P<holder>[A-Za-z][A-Za-z0-9_-]*)\s+(?P<rest>.+)$", raw)
        if not m:
            return None
        holder = m.group("holder").lower()
        rest = m.group("rest").strip()

        families = (
            ("goal", cls.GOAL_PATTERNS, 0.70),
            ("fear", cls.FEAR_PATTERNS, 0.70),
            ("expectation", cls.EXPECT_PATTERNS, 0.55),
        )
        for kind, patterns, priority in families:
            for regex in patterns:
                mm = regex.match(rest)
                if not mm:
                    continue
                prop = cls._strip_coref(rest[mm.end():], holder)
                if not prop:
                    return None
                return {
                    "holder": holder,
                    "kind": kind,
                    "proposition_text": prop,
                    "priority": priority,
                    "confidence": 0.84,
                    "source": "mental_language",
                }
        return None

    @classmethod
    def parse_self_outcome(cls, text: str) -> Optional[dict]:
        raw = cls._clean(text).lower()
        failure = bool(cls.SELF_FAIL.search(raw))
        success = bool(cls.SELF_SUCCESS.search(raw))
        if failure == success:
            return None

        # Restrict implicit self-updates to explicitly self-referential reports,
        # except for a leading named strategy followed by a success/failure verb.
        self_ref = bool(re.search(r"\b(?:i|my|myself)\b", raw))
        strategy = None

        patterns = (
            r"\bi\s+(?:tried|used|tested|ran|chose)\s+(?P<s>[a-z0-9_+-]+)",
            r"\bmy\s+(?P<s>[a-z0-9_+-]+)\s+strategy\b",
            r"^(?P<s>[a-z0-9_+-]+)\s+(?:strategy\s+)?(?:worked|failed|succeeded|passed)\b",
        )
        for pat in patterns:
            m = re.search(pat, raw)
            if m:
                strategy = m.group("s")
                break

        if not strategy or (not self_ref and not re.match(r"^[a-z0-9_+-]+\s+", raw)):
            return None

        # General-purpose task-family hints.  If none is present this is a
        # reasoning strategy report, matching ASM's core metacognitive use.
        task = "reasoning"
        for name in ("coding", "search", "planning", "math", "memory", "perception"):
            if re.search(rf"\b{name}\b", raw):
                task = name
                break

        return {
            "task_family": task,
            "strategy": strategy,
            "success": success and not failure,
            "confidence": 0.88,
            "source": "mental_language",
        }
