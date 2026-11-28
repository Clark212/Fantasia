# ASM v0.4.0-alpha.8.0-DEV1 — Hybrid Learning Infrastructure

**Status:** experimental development branch, not an official release.  
**Parent:** frozen `v0.4.0-alpha.7.9`.  
**Scope:** foundational experience representation, bounded intake, dataset parsing/splitting, simulation episode capture, evidence-aware review ranking, and prediction metrics.

## Compatibility and safety boundaries

- The parent Alpha 7.9 release remains unchanged and is preserved in this archive under `baseline/ASM_v0.4.0-alpha.7.9.zip`.
- `asm.__version__` remains `0.4.0-alpha.7.9`. This DEV1 branch does not claim Alpha 8 stage completion.
- The new package is imported explicitly with `from asm.learning import ...`; it is not automatically wired into ASM beliefs, semantic memory, action selection, or procedure activation.
- Generated examples are marked as generated and are not treated as independent observed evidence.
- Dataset splitting is deterministic and group-aware. Split by a stable task/group identifier before fitting or tuning; do not use test records for training, replay, abstraction selection, or threshold tuning.
- The in-memory store is bounded and intentionally drops the oldest item when capacity is exceeded. It is a prototype store, not yet a durable persistent memory backend.
- Simulation policies receive only the observation mapping. The runner does not expose environment internals.

## New modules

| Module | Purpose |
|---|---|
| `asm/learning/experience.py` | Validated canonical experience record and content fingerprint |
| `asm/learning/store.py` | Thread-safe bounded store with duplicate rejection |
| `asm/learning/ingestion.py` | Streaming CSV/JSONL ingestion and deterministic splits |
| `asm/learning/simulation.py` | Environment protocol and bounded episode runner |
| `asm/learning/integration.py` | Intake and review prioritization; no automatic belief promotion |
| `asm/learning/evaluation.py` | Exact-match count and numeric MAE for comparable prediction fields |

## Quick start

```python
from asm.learning import Experience, ExperienceStore, ExperienceIntegrator

store = ExperienceStore(capacity=50_000)
integrator = ExperienceIntegrator(store)
record = Experience(
    experience_id="math-0001",
    source="dataset",
    domain="mathematics",
    task_id="linear-equation-family-01",
    observation={"equation": "2x + 3 = 7"},
    outcome={"solution": 2},
    evidence_status="labeled",
)
print(integrator.ingest([record]))
print(integrator.review_queue(limit=10))
```

CSV and JSONL loaders expect canonical records with `experience_id`, `domain`, `task_id`, and JSON-compatible `observation`; optional fields include `prediction`, `outcome` (or legacy `actual_outcome`), `evidence_status`, `timestamp`, and `metadata`.

## DEV1 validation

Run:

```bash
python -m pytest -q tests/test_alpha8_hybrid_learning.py
python -m pytest -q tests/test_alpha79_release.py tests/test_alpha79_signed_latent.py
```

Passing these tests demonstrates only the tested software contracts. It does not establish improved general intelligence, broad transfer, or an Alpha 8 release pass.

## Next work

1. DEV2: durable append-only experience persistence, schema migration, provenance checks, dataset manifests and leakage audits.
2. DEV3: controlled simulation environments and prediction-error calibration.
3. DEV4: candidate structural discovery and independent transfer evaluation.
4. DEV5: replay scheduling, retention and forgetting tests.
5. DEV6: carefully gated integration with existing ASM cognitive systems.

Each step requires a review and regression gate before proceeding.
