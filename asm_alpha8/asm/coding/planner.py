"""Conservative coding-task decomposition from repository evidence."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from .analyzer import RepositoryReport


@dataclass
class CodingPlan:
    task: str
    task_type: str
    confidence: float
    repository_fingerprint: str
    relevant_files: list[str] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    cautions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


class CodingTaskPlanner:
    """Create explainable plans; it does not edit files or execute commands."""
    INTENTS = {
        "debug": (r"\b(debug|bug|error|exception|crash|traceback|fail(?:s|ed|ing)?)\b", 0.88),
        "add_feature": (r"\b(add|implement|create|build|support|introduce)\b", 0.72),
        "refactor": (r"\b(refactor|restructure|simplify|clean\s+up|optimi[sz]e)\b", 0.78),
        "test": (r"\b(test|tests|coverage|regression|verify)\b", 0.82),
        "explain": (r"\b(explain|understand|what\s+does|how\s+does|where\s+is)\b", 0.76),
    }

    def plan(self, task: str, report: RepositoryReport) -> CodingPlan:
        if not task or not task.strip():
            raise ValueError("task must not be empty")
        text = task.strip()
        low = text.lower()
        ranked = [(kind, confidence) for kind, (pattern, confidence) in self.INTENTS.items()
                  if re.search(pattern, low)]
        if ranked:
            kind, confidence = ranked[0]
        else:
            kind, confidence = "investigate", 0.45

        tokens = {t for t in re.findall(r"[a-z_][a-z0-9_]{2,}", low)
                  if t not in {"the", "and", "for", "with", "from", "that", "this", "into", "please"}}
        scored = []
        for file in report.files:
            haystack = " ".join([file.path] + [s.name for s in file.symbols] + file.imports + file.calls).lower()
            score = sum(1 for token in tokens if token in haystack)
            if score:
                scored.append((score, file.path))
        relevant = [p for _, p in sorted(scored, key=lambda x: (-x[0], x[1]))[:8]]
        evidence = [f"Repository fingerprint: {report.fingerprint}",
                    f"Indexed {report.scanned_files} Python files and {sum(len(f.symbols) for f in report.files)} symbols."]
        if relevant:
            evidence.append("Relevant paths matched task vocabulary: " + ", ".join(relevant))
        else:
            evidence.append("No strong filename/symbol match; begin with a broader repository search.")

        steps_by_kind = {
            "debug": ["Reproduce the failure and capture the complete traceback.",
                      "Trace the failing symbol through callers and dependencies.",
                      "Form a minimal root-cause hypothesis and identify a regression test.",
                      "Make the smallest isolated change, then rerun focused and regression tests."],
            "add_feature": ["Locate the owning module and its public interfaces.",
                            "Define expected behavior, edge cases, and compatibility constraints.",
                            "Add a focused test before implementing the feature.",
                            "Implement the smallest coherent change and validate regressions."],
            "refactor": ["Map current callers, imports, and public symbols before changing structure.",
                         "Record behavior-preserving tests for the affected interfaces.",
                         "Refactor in small steps while preserving public contracts.",
                         "Compare test results and dependency structure before and after."],
            "test": ["Identify the public behavior and existing test conventions.",
                     "Add deterministic tests for normal, boundary, and failure cases.",
                     "Include a negative control that would fail if the implementation were bypassed.",
                     "Run focused tests followed by the relevant regression suite."],
            "explain": ["Start from the relevant module and its public symbols.",
                        "Trace imports and callers to establish control and data flow.",
                        "Separate directly observed behavior from inferred intent."],
            "investigate": ["Search the repository for the named feature, symbols, and related tests.",
                            "Map callers, dependencies, and current behavior before proposing edits.",
                            "State uncertainties and request missing reproduction details if needed."],
        }
        cautions = ["This planner is heuristic: its file ranking is a lead, not proof of relevance.",
                    "Static indexing does not execute code, prove correctness, or inspect runtime behavior.",
                    "No files have been modified and no commands have been run."]
        if any(d.severity == "error" for d in report.diagnostics):
            cautions.append("The repository already contains static-analysis errors; distinguish pre-existing issues from new ones.")
        return CodingPlan(text, kind, confidence, report.fingerprint, relevant,
                          steps_by_kind[kind], evidence, cautions)
