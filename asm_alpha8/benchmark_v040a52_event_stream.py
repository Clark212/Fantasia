"""Deterministic alpha.5.2 event-stream architecture benchmark.

Measures only current-branch event-processing throughput. Historical BEFORE numbers
are documented in ARCHITECTURE_ALPHA5_2_REPORT.md because reproducing those requires
running the preserved older artifacts.
"""
import json, random, tempfile, time
from pathlib import Path
from asm import ASMEngine, ASMConfig, __version__

rng = random.Random(1337)
vocab = [f"w{i}" for i in range(72)]
texts = []
for _ in range(160):
    a,b,c,d,e,f,g,h = rng.sample(vocab, 8)
    texts.append(f"{a} {b} {c} {d}; {e} {f} {g} {h}")

with tempfile.TemporaryDirectory() as td:
    engine = ASMEngine(Path(td) / "stress.db", config=ASMConfig(snapshot_every_events=999999))
    ms = []
    signature = []
    for text in texts:
        start = time.perf_counter()
        result = engine.process(text, training=True)
        ms.append((time.perf_counter() - start) * 1000.0)
        stats = result.get("stats", {})
        signature.append((
            result.get("decision"),
            stats.get("discovered_relations"),
            stats.get("relation_merges"),
            stats.get("relation_splits"),
        ))
    payload = {
        "version": __version__,
        "events": len(texts),
        "total_ms": sum(ms),
        "first10_mean_ms": sum(ms[:10]) / 10.0,
        "last10_mean_ms": sum(ms[-10:]) / 10.0,
        "p50_ms": sorted(ms)[len(ms)//2],
        "max_ms": max(ms),
        "relation_stats": engine.relation_discovery.stats(),
        "signature_length": len(signature),
        "claim_boundary": "Throughput benchmark only; it does not measure intelligence or language quality.",
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
