from __future__ import annotations

import json
import math
import tempfile
import time
from pathlib import Path

from asm import ASMEngine, __version__

CASES = [
    ("Vera firmly reckons that the route is safe", "belief"),
    ("Noah eventually found out that the token is valid", "belief"),
    ("Ava now reckons Ben thinks the gate is open", "nested_belief"),
    ("Kai remains certain Mia believes the key is hidden", "nested_belief"),
    ("Evan has really been hoping that the mission succeeds", "drive"),
    ("Gina is still afraid that the storm continues", "drive"),
    ("Theo had anticipated that the project succeeds", "drive"),
    ("after retrying I ran simulation and it succeeded", "self_outcome"),
    ("after retrying I ran analogy and it failed", "self_outcome"),
    ("the processor became unusually warm", "other"),
    ("a document is still inside the cabinet", "other"),
    ("pressure increases temperature", "other"),
    ("Mira firmly reckons that the lamp is on", "belief"),
    ("Iris now reckons Omar thinks the box is empty", "nested_belief"),
    ("Fiona has really been hoping that the project succeeds", "drive"),
    ("Hugo is still afraid that the danger remains", "drive"),
    ("after retrying I ran search and it succeeded", "self_outcome"),
    ("after retrying I ran planning and it failed", "self_outcome"),
    ("the sensor reports voltage", "other"),
    ("rain fell during the night", "other"),
]

started = time.perf_counter()
with tempfile.TemporaryDirectory() as td:
    asm = ASMEngine(Path(td) / "bench.db")
    rows = []
    high = []
    for text, expected in CASES:
        read = asm._read_language(text)
        got = read.metadata.get("intent")
        conf = float(read.metadata.get("intent_confidence", 0.0))
        ok = got == expected
        rows.append({"text": text, "expected": expected, "got": got, "confidence": conf, "pass": ok})
        if conf >= asm.cfg.language_core_recurrent_min_intent_confidence:
            high.append(ok)

    # End-to-end tests ensure the reader is not dead code.
    before = asm.capability("reasoning")["attempts"]
    result = asm.process("I tried analogy and it failed", training=True)
    after = asm.capability("reasoning")["attempts"]
    graph_has_neural = any(k.startswith("LCORE:EMB:") for k in asm.field.nodes)
    end_to_end = {
        "self_outcome_updated": after == before + 1,
        "neural_proposal_accepted": len(result["language_core"]["accepted"]) == 1,
        "neural_embedding_in_graph": graph_has_neural,
    }
    status = asm.language_core_status()
    asm.close()

passed = sum(int(r["pass"]) for r in rows)
selective = (sum(int(x) for x in high) / len(high)) if high else 0.0
payload = {
    "version": __version__,
    "benchmark": "ASM v0.2.0-alpha.2 recurrent reader held-out composition benchmark",
    "cases": len(rows),
    "accuracy_pct": round(100 * passed / len(rows), 2),
    "confidence_threshold": 0.80,
    "selective_cases": len(high),
    "selective_accuracy_pct": round(100 * selective, 2),
    "end_to_end": end_to_end,
    "backend_status": status,
    "elapsed_seconds": round(time.perf_counter() - started, 3),
    "rows": rows,
    "notes": [
        "This is an assistant-authored local benchmark, not an external standardized language benchmark.",
        "The recurrent reader classifies broad semantic intent families; exact slot extraction still uses ASM's safe deterministic slotter in alpha.2.",
        "RWKV-7 checkpoint inference was not executed in this build environment because the runtime/checkpoint were unavailable locally.",
    ],
}
out = Path('/mnt/data/ASM_v0.2.0-alpha.2_recurrent_benchmark.json')
out.write_text(json.dumps(payload, indent=2), encoding='utf-8')
print(json.dumps({k:v for k,v in payload.items() if k != 'rows'}, indent=2))
print('RESULT:', out)
