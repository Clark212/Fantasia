from __future__ import annotations

from dataclasses import dataclass
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence

from .encoder import light_stem, STOPWORDS
from .mental_language import MentalLanguagePerception


@dataclass(slots=True)
class DialogueAct:
    label: str
    confidence: float
    source: str
    probabilities: Dict[str, float]

    def as_dict(self) -> dict:
        return {
            "label": self.label,
            "confidence": self.confidence,
            "source": self.source,
            "probabilities": dict(self.probabilities),
        }


class DialogueActRecognizer:
    """
    Conservative conversational act router.

    This layer is intentionally small and deterministic. It does not pretend to
    be the learned language model: ASM's frozen recurrent reader remains the
    learned input representation. This router only decides how to surface common
    conversational moves safely.
    """

    def __init__(self):
        self._ready=True

    @staticmethod
    def _norm(text: str) -> str:
        return " ".join(text.lower().replace("’","'").strip().split())

    def recognize(self,text: str) -> DialogueAct:
        t=self._norm(text).strip(" .!?")
        tests=(
            ("memory_query", r"\b(?:remember|recall)\b|\bwhat did i (?:just\s+)?(?:say|tell)\b|\bwhat do you remember\b|\bwhat was i talking about\b|\bwhat was my last message\b", 0.99),
            ("belief_query", r"\bwhat does \w+ (?:believe|think|assume|expect)\b|^(?:does|did)\s+\w+\s+(?:believe|think|assume|expect)\b|\btell me (?:what )?\w+(?:'s)? belief\b|\bwhat is \w+(?:'s)? belief\b", 0.99),
            ("wellbeing", r"^(?:how (?:are|r|have) you|how(?:'s| is) it going|you (?:good|alright|okay)|are you (?:okay|alright)|how do you feel)\b", 0.99),
            ("identity", r"^(?:who are you|what are you|what is asm|who is asm|tell me about yourself|describe yourself|are you (?:an? )?(?:ai|llm|chatbot))\b", 0.99),
            ("gratitude", r"^(?:thanks|thank you|thx|ty|much appreciated|appreciate it)\b", 0.99),
            ("farewell", r"^(?:bye|goodbye|cya|see ya|see you|later|good night|night)\b", 0.99),
            ("greeting", r"^(?:hi|hello|hey|yo|hiya|sup|wassup|good morning|good afternoon|good evening)\b", 0.99),
            ("negative_affect", r"\b(?:angry|mad|annoyed|upset|frustrated|irritated|hate)\b", 0.97),
            ("positive_affect", r"\b(?:happy|excited|glad|awesome|proud|feeling good|feel great)\b", 0.97),
        )
        for label,pat,conf in tests:
            if re.search(pat,t,re.I):
                return DialogueAct(label,conf,"conversation-router",{})
        if text.rstrip().endswith("?") or re.match(
            r"^(?:why|how|what|when|where|who|can|could|is|are|do|does|did|should|would)\b",
            t,
        ):
            return DialogueAct("question",0.92,"question-shape",{})
        return DialogueAct("other",0.70,"conversation-router",{})

    def health(self)->dict:
        return {
            "ready":True,
            "learned_dialogue_classifier":False,
            "architecture":"safe dialogue router + ASM recurrent language reader",
            "note":"Surface routing is deterministic; learned language perception remains in the recurrent reader.",
        }


class ConversationManager:
    """Session dialogue state + ASM-grounded surface realization."""

    def __init__(self, recognizer: DialogueActRecognizer, *, history_limit: int = 16):
        self.recognizer=recognizer
        self.history_limit=max(4,int(history_limit))
        self.history: List[dict] = []

    @staticmethod
    def _clean_prop(prop: str) -> str:
        return " ".join(str(prop).replace("_"," ").split())

    @staticmethod
    def _content_stems(text: str) -> set[str]:
        words=re.findall(r"[A-Za-z0-9']+",text.lower())
        return {
            light_stem(w)
            for w in words
            if w not in STOPWORDS and len(w)>1
        }

    def _memory_search(self, engine, text: str, limit: int = 3) -> List[dict]:
        # Alpha.7 prefers explicit event/entity/proposition evidence.  Legacy
        # lexical recall remains a fallback so older and untyped memories are not
        # lost during migration.
        structured = engine.event_memory.recall(text, limit=max(limit * 2, limit))
        observed=engine.encoder.encode(text,semantic_expand=True)
        remove={"remember","recall","said","say","tell","told","what","thing","about","before"}
        observed={
            k:v for k,v in observed.items()
            if not any(f":{word}" in k.lower() for word in remove)
            and not str(k).startswith(("ATTEND:","SELFSTATE:","LCORE:"))
        }
        lexical=engine.memory.recall(observed,limit=max(limit*2,limit))
        merged=[]
        seen=set()
        for row in structured + lexical:
            if row["id"] in seen:
                continue
            seen.add(row["id"]); merged.append(row)
            if len(merged) >= limit:
                break
        return merged

    def _belief_answer(self, engine, text: str) -> str | None:
        t=text.lower()
        m=re.search(
            r"(?:what does|tell me(?: what)?|what is)\s+([a-z][a-z0-9_-]*)"
            r"(?:'s)?\s*(?:believe|think|assume|expect|belief)?(?:\s+about)?\s*(.*?)[?.!]*$",
            t,
            re.I,
        )
        if not m:
            m=re.search(r"what does\s+([a-z][a-z0-9_-]*)\s+(?:believe|think)(?:\s+about)?\s*(.*?)[?.!]*$",t,re.I)
        if not m:
            m=re.search(r"^(?:does|did)\s+([a-z][a-z0-9_-]*)\s+(?:believe|think|assume|expect)(?:\s+that)?\s*(.*?)[?.!]*$",t,re.I)
        if not m:
            return None
        holder=m.group(1).lower()
        topic=(m.group(2) or "").strip()
        topic_stems=self._content_stems(topic)

        # Alpha.7 typed memory can distinguish belief/expectation/fear/goal
        # before falling back to lexical episode matching.
        structured = engine.event_memory.recall(text, limit=4)
        if structured:
            best = structured[0]
            if best.get("event_type") in {"belief", "nested_belief", "expectation", "fear", "goal"}:
                original = str(best.get("text", "")).strip().rstrip(".!?")
                if original:
                    return f"I remember you told me: {original}."

        # Prefer the original episodic wording for human-facing language.
        observed=engine.encoder.encode(text,semantic_expand=True)
        for row in engine.memory.recall(observed,limit=12):
            original=str(row.get("text","")).strip()
            low=original.lower()
            if holder not in low:
                continue
            if not re.search(r"\b(?:believes?|thinks?|assumes?|expects?|suspects?)\b",low):
                continue
            original_stems=self._content_stems(original)
            if topic_stems and not (topic_stems & original_stems):
                continue
            return f"I remember you told me: {original.rstrip('.!?')}."

        states=engine.minds.states.get(holder,{})
        if not states:
            return f"I don't have a stored belief for {holder.title()} yet."

        ranked=[]
        for prop in states:
            p_stems=self._content_stems(prop)
            overlap=len(topic_stems & p_stems) if topic_stems else 0
            score=(overlap/max(1,len(topic_stems))) if topic_stems else 0.25
            state=engine.minds.query_base(holder,prop)
            score += 0.15*float(state.get("confidence",0.0))
            ranked.append((score,prop,state))
        ranked.sort(key=lambda x:x[0],reverse=True)
        if not ranked or ranked[0][0] < 0.15:
            return f"I don't have a clear stored belief from {holder.title()} about that."
        _,prop,state=ranked[0]
        if state.get("truth") is True:
            return f"I remember that {holder.title()} believes that {self._clean_prop(prop)}."
        if state.get("truth") is False:
            return f"I remember that {holder.title()} believes that {self._clean_prop(prop)} is false."
        return f"{holder.title()}'s stored belief about {self._clean_prop(prop)} is uncertain."

    def _structured_ack(self,text: str,result: Mapping[str,Any]) -> str | None:
        nested=result.get("nested_belief_event")
        mind=result.get("mind_event")
        drive=result.get("drive_event")
        outcome=result.get("self_language_outcome")

        # Alpha.6: prefer the typed event's preserved surface proposition for
        # human-facing language. Canonical stems remain internal cognition only.
        sem = result.get("semantic_event", {}).get("primary", {})
        sem_type = str(sem.get("event_type", ""))
        if sem and sem.get("persistent_eligible") is False:
            return None
        sem_prop = sem.get("proposition") or {}
        surface = str(sem_prop.get("surface", "")).strip()
        truth = sem_prop.get("truth")
        agents = [str(x).title() for x in sem.get("agents", []) if str(x)]
        if surface and sem_type == "nested_belief" and len(agents) >= 2:
            if len(agents) == 2:
                chain = f"{agents[0]} thinks {agents[1]} believes that {surface}"
            else:
                chain = " thinks ".join(agents[:-1]) + f" thinks {agents[-1]} believes that {surface}"
            return f"Got it. I'll remember that {chain}."
        if surface and sem_type == "belief" and agents:
            if truth is False:
                return f"Got it. I'll remember that {agents[0]} doubts that {surface}."
            return f"Got it. I'll remember that {agents[0]} believes that {surface}."
        if surface and sem_type in {"goal", "fear", "expectation"} and agents:
            if sem_type == "fear":
                return f"Got it. I'll remember that {agents[0]} is concerned about {surface}."
            if sem_type == "expectation":
                return f"Got it. I'll remember that {agents[0]} expects {surface}."
            return f"Got it. I'll remember that {agents[0]} wants {surface}."

        if nested and int(nested.get("order",0))>1:
            path=[str(x).title() for x in nested.get("path",[])]
            if len(path)>=2:
                chain=" thinks ".join(path)
                truth="" if nested.get("asserted_truth",True) else "not "
                return f"Got it. I'll remember that {chain} believes that {truth}{self._clean_prop(nested.get('proposition','that'))}."

        if mind and mind.get("type")=="belief":
            surface=MentalLanguagePerception.parse_direct_belief(text)
            if surface:
                holder=str(surface.get("holder","someone")).title()
                proposition=str(surface.get("proposition_text","that")).strip().rstrip(".!?")
                return f"Got it. I'll remember that {holder} believes that {proposition}."
            holder=str(mind.get("holder","someone")).title()
            truth="" if mind.get("asserted_truth",True) else "not "
            return f"Got it. I'll remember {holder}'s belief about {truth}{self._clean_prop(mind.get('proposition','that'))}."

        if drive:
            holder=str(drive.get("holder","someone")).title()
            kind=str(drive.get("kind","goal"))
            prop=self._clean_prop(drive.get("proposition","that"))
            if not drive.get("desired_truth", True):
                prop = "not " + prop
            # Keep original scoped wording when ASM has accepted the matching
            # drive; canonical stems can lose natural negation/auxiliaries.
            surface = MentalLanguagePerception.parse_drive(text)
            accepted = result.get("language_core", {}).get("accepted", [])
            for candidate in accepted:
                if candidate.get("kind") == "drive":
                    surface = candidate.get("payload")
                    break
            if surface and str(surface.get("holder", "")).lower() == str(drive.get("holder", "")).lower() and surface.get("kind") == kind:
                prop = str(surface["proposition_text"]).strip().rstrip(".!?")
            if kind=="fear":
                return f"Got it. I'll remember that {holder} is concerned about {prop}."
            if kind=="expectation":
                return f"Got it. I'll remember that {holder} expects {prop}."
            return f"Got it. I'll remember that {holder} wants {prop}."

        if outcome:
            out=outcome.get("outcome",{})
            strategy=str(out.get("strategy","that strategy")).replace("_"," ")
            success=bool(out.get("success"))
            return (
                f"I updated my self-model: {strategy} worked."
                if success else
                f"I updated my self-model: {strategy} failed."
            )
        return None

    def respond(self, text: str, result: Mapping[str,Any], engine) -> dict:
        from .cognitive_packet import build_packet, hybrid_generate
        packet = build_packet(text, result, engine, self)
        act = self.recognizer.recognize(text)
        if engine.writer is None:
            generation = {"text": hybrid_generate(packet), "backend": "hybrid",
                          "learned_generation": False, "fallback": False}
        else:
            try:
                generation = engine.writer.generate(packet)
            except Exception as exc:
                generation = {"text": hybrid_generate(packet), "backend": "hybrid-fallback",
                              "learned_generation": False, "fallback": True,
                              "fallback_reason": f"{type(exc).__name__}: {exc}"}
        reply = generation["text"]
        self.history.append({"user": text, "reply": reply, "act": act.as_dict()})
        self.history = self.history[-self.history_limit:]
        return {"reply": reply, "act": act.as_dict(), "history_length": len(self.history),
                "grounded": bool(packet.evidence), "packet": packet.as_dict(), "writer": generation}

    def state(self)->dict:
        return {
            "history_length":len(self.history),
            "recent":self.history[-6:],
            "recognizer":self.recognizer.health(),
        }
