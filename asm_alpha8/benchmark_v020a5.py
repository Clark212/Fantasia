"""Fixed novel-content comparison. Quality metrics are explicit task checks,
not a human fluency score, intelligence score or GPT-relative percentage.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import tempfile
import time


def rss_mib():
    try:
        for line in Path("/proc/self/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) / 1024
    except OSError:
        pass
    return None


# Authored AFTER the writer training corpus; no new facts are retrained.
CASES = [
    ("hello", ["Hey"], []),
    ("how are you", ["internal confidence signal", "curiosity signal"], ["I feel"]),
    ("who are you", ["memory-centric", "recurrent"], []),
    ("thanks", ["welcome"], []),
    ("Where is the brass telescope?", ["enough"], ["brass telescope is"]),
    ("Selene believes the umber hatch is locked", ["Selene", "locked"], []),
    ("what does Selene believe about the umber hatch?", ["Selene", "locked"], []),
    ("what does Imani believe about the umber hatch?", ["don't have", "Imani"], ["Imani believes"]),
    ("The quartz turbine overheated after prolonged operation", ["memory"], []),
    ("what did i say about the quartz turbine?", ["quartz turbine overheated"], []),
    ("what did i just say?", ["what did i say about the quartz turbine?"], []),
    ("rzzkk", ["not sure what you mean"], []),
    ("im upset about the delay", ["upset"], []),
    ("I'm happy", [], []),
    ("bye", ["See you"], []),
]


def worker(backend):
    from asm import ASMConfig, ASMEngine
    from asm.cognitive_packet import CognitivePacket, hybrid_generate
    from asm.recurrent_writer import ACTIONS, RecurrentWriter
    start = time.perf_counter()
    with tempfile.TemporaryDirectory() as td:
        engine = ASMEngine(Path(td) / "bench.db", ASMConfig(writer_backend=backend))
        startup_ms = (time.perf_counter() - start) * 1000
        rss_ready = rss_mib()
        outputs = []
        for text, required, forbidden in CASES:
            t = time.perf_counter()
            result = engine.chat(text)
            elapsed = (time.perf_counter() - t) * 1000
            reply = result["reply"]
            writer = result["conversation"]["writer"]
            packet = result["conversation"]["packet"]
            outputs.append({"input": text, "reply": reply, "packet": packet,
                            "pass": all(w.lower() in reply.lower() for w in required)
                            and not any(w.lower() in reply.lower() for w in forbidden),
                            "fallback": writer["fallback"], "conversation_ms": elapsed,
                            "writer_ms": writer.get("elapsed_ms")})
        engine.close()
    # Only direct grounding / abstention cases have an unsupported-claim oracle.
    # This does not pretend that surface token fidelity proves arbitrary truth.
    claim_cases = [r for r in outputs if r["packet"]["user_intent"] in
                   {"belief_report", "cognitive_report", "memory_report", "previous_message", "uncertainty", "wellbeing"}]
    unsupported = sum(not r["pass"] for r in claim_cases)
    writer = RecurrentWriter() if backend == "recurrent" else None
    samples, missing = [], 0
    for i in range(100):
        claim = f"Novel agent Zelmira-{i} reported that device VX-{i*179+7} reached {i+19} units."
        packet = CognitivePacket("memory_report", {"claim": claim}, style="brief" if i % 2 else "full")
        t = time.perf_counter()
        out = writer.generate(packet) if writer else {"text": hybrid_generate(packet), "fallback": False}
        samples.append((time.perf_counter() - t) * 1000)
        missing += int(claim not in out["text"] or out["fallback"])
    ordered = sorted(samples)
    return {"backend": backend, "startup_ms": startup_ms, "rss_ready_mib": rss_ready,
            "rss_end_mib": rss_mib(), "writer_median_ms": statistics.median(samples),
            "writer_p95_ms": ordered[int(.95 * (len(ordered)-1))],
            "behavior_passed": sum(r["pass"] for r in outputs), "behavior_total": len(outputs),
            "fallback_count": sum(r["fallback"] for r in outputs),
            "exact_content_preserved": 100-missing, "novel_content_cases": 100,
            "unsupported_claim_cases": unsupported, "claim_audited_cases": len(claim_cases),
            "unsupported_claim_rate": unsupported / max(1, len(claim_cases)), "cases": outputs}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", choices=["hybrid", "recurrent"])
    args = parser.parse_args()
    if args.worker:
        print(json.dumps(worker(args.worker)))
        return
    runs = []
    env = dict(os.environ, OMP_NUM_THREADS="1", MKL_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1")
    for backend in ["hybrid", "recurrent"]:
        proc = subprocess.run([sys.executable, __file__, "--worker", backend], capture_output=True, text=True, env=env, check=True)
        runs.append(json.loads(proc.stdout))
    result = {"benchmark": "alpha.5 hybrid versus learned writer", "platform": platform.platform(),
              "python": platform.python_version(), "cpu_count": os.cpu_count(), "runs": runs,
              "scope": "authored speech-act checks and exact novel-content preservation; no independent fluency ratings",
              "gpt_5_6_sol": {"measured": False, "comparison": None},
              "not_measured": ["general intelligence", "AGI percentage", "Pi 5 performance", "unrestricted free language generation"]}
    out = Path(__file__).parent / "results/writer_benchmark.json"
    out.write_text(json.dumps(result, indent=2))
    print(json.dumps([{k:v for k,v in r.items() if k != "cases"} for r in runs], indent=2))


if __name__ == "__main__":
    main()
