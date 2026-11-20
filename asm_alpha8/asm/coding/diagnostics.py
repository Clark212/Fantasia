"""Evidence-based pytest failure extraction and source localization."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class FailureEvidence:
    test_id: str
    exception: str | None = None
    message: str = ""
    traceback_locations: list[dict] = field(default_factory=list)
    likely_source_files: list[str] = field(default_factory=list)
    confidence: float = 0.0
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


class FailureAnalyzer:
    """Parse common pytest output formats; never claim a root cause from a trace alone."""
    FAILED = re.compile(r"^FAILED\s+(.+?)(?:\s+-\s+(.+))?$", re.M)
    FRAME = re.compile(r'^\s*(.+?\.py):([0-9]+): in (.+?)\s*$', re.M)
    EXCEPTION = re.compile(r"^([A-Za-z_][\w.]*?(?:Error|Exception|Failure))(?::\s*(.*))?$", re.M)

    def analyze(self, output: str, root: str | Path) -> list[FailureEvidence]:
        base = Path(root).resolve(strict=True)
        failures = list(self.FAILED.finditer(output or ""))
        if not failures and not output.strip():
            return []
        blocks = []
        if failures:
            for i, match in enumerate(failures):
                end = failures[i + 1].start() if i + 1 < len(failures) else len(output)
                blocks.append((match.group(1).strip(), match.group(2) or "", output[match.start():end]))
        else:
            blocks.append(("<unparsed pytest output>", "", output))
        results = []
        for test_id, summary, block in blocks:
            locations = []
            likely = []
            reasons = []
            frame_source = block if self.FRAME.search(block) else output
            for frame in self.FRAME.finditer(frame_source):
                raw_path = frame.group(1).strip()
                path = Path(raw_path)
                if not path.is_absolute():
                    path = base / path
                try:
                    resolved = path.resolve(strict=False)
                    if resolved.is_relative_to(base):
                        rel = resolved.relative_to(base).as_posix()
                        locations.append({"path": rel, "line": int(frame.group(2)), "function": frame.group(3)})
                        if rel not in likely and not rel.startswith("tests/"):
                            likely.append(rel)
                except (OSError, ValueError):
                    continue
            exc_match = self.EXCEPTION.search(block) or self.EXCEPTION.search(output)
            exception = exc_match.group(1) if exc_match else None
            message = (exc_match.group(2) if exc_match else summary).strip()
            if likely:
                reasons.append("Non-test traceback frames point to these repository files.")
            if exception:
                reasons.append("Exception class and message were extracted from pytest output.")
            if not likely:
                reasons.append("No in-repository production frame was confidently localized; inspect the test and full traceback.")
            results.append(FailureEvidence(test_id, exception, message[:1000], locations,
                                           likely[:8], 0.75 if likely else 0.25, reasons))
        return results
