# ASM v0.4.0-alpha.8.0-DEV2.1 — Durable, Auditable Experience Storage (fix release)

**Status:** experimental development branch, not an official release.
**Parent:** `ASM_alpha8_DEV1.zip` (sha256 ba3654f5fdb18d38…). **Supersedes** the first `ASM_alpha8_DEV2.zip` (sha256 786e46c02a2c6682…), which had the bug described under *Fix history*. `asm.__version__` is unchanged (`0.4.0-alpha.7.9`).
Not wired into ASM beliefs, memory or action selection. No Alpha 8 stage claim.

## Added: `asm/learning/persistence.py`
| Item | What it does |
|---|---|
| `ExperienceLog(path, fsync=True, repair_torn_tail=False, integrity="full")` | Append-only JSONL. Each entry: schema, seq, prev hash, own hash, record. Rejects duplicate id/fingerprint (same rule as `ExperienceStore`). |
| `verify()` | Re-scans the file; reports edits, deletions, reordering, truncation, unknown schema. Never mutates. |
| `import_file()` / `load_into(store)` | Append a DEV1 CSV/JSONL dataset; load the log into a bounded `ExperienceStore`. |
| `manifest()` / `write_manifest()` | Entry count, head hash, file sha256, domain/source/evidence counts, independent vs generated/inferred counts, split sizes, leakage audit. |
| `audit_leakage(splits)` | Flags: task in >1 split; same fingerprint across splits; same (domain, observation) in train and validation/test; generated/inferred records in validation/test. |
| `check_external_changes()` | True if the file is exactly what this writer last saw; raises `LogCorruptionError` otherwise. |
| `LogCorruptionError` | Raised on open/read of a failed log; a corrupt log refuses appends. |

## Limits (read these)
- The hash chain is tamper **evidence**, not proof: a full rewrite with recomputed hashes is undetectable unless the
  `head_hash` is stored independently (e.g. in a release record or separate system).
- Single writer process (thread-safe in-process). Before every `append`, and once per `append_many` batch, the writer refuses
  to write if the file is no longer what it last saw (nothing is written; the refusal persists until reopened and verified):
  - `integrity="full"` (default): file identity (device+inode), size, and SHA-256 of every byte already in the file. Catches
    same-length edits, edits with a restored mtime, truncation, appended bytes, replacement (even byte-identical), deletion.
    Cost: one read of the file per `append` call (~6.8 ms on a 7.9 MB / 20,000-entry log). Use `append_many` for bulk loads
    (20,000 entries in ~1 s with a single check).
  - `integrity="metadata"` (opt-in, O(1), ~0.06 ms): identity, size, mtime_ns, ctime_ns and a re-hash of the last entry.
    **Can miss** an edit to an older entry made within the filesystem timestamp granularity of the previous write, and relies on
    ctime being a change time (not true on Windows). A test pins this known limit. `verify()` and reopen still catch it.
  - Not covered: a second process writing at the same instant (detected only after the fact), and anyone with the ability to
    rewrite the file AND this process's memory. Replacement of the whole file by a validly chained copy is only detectable
    through an independently stored `head_hash`.
- Opening, `records()` and `manifest()` scan the whole file: about 0.6 s per 20,000 entries (7.9 MB) on the test machine.
  Fine for tens of thousands of records; would need an index for millions.
- Schema migration is a **hook only** (`MIGRATIONS`, empty). Only schema 1 exists; any other version is rejected explicitly.
- Torn-tail repair truncates only an incomplete final line. A complete but corrupt entry is never "repaired".
- The audit checks exact matches only. It does not detect near-duplicates or paraphrased leakage.
- Provenance is whatever the records claim (`source`, `evidence_status`); nothing here verifies those claims are true.

## Run
    python -m pytest -q tests/test_alpha8_dev2_persistence.py tests/test_alpha8_hybrid_learning.py \
        tests/test_alpha79_release.py tests/test_alpha79_signed_latent.py

## Next (roadmap)
DEV3 controlled simulation environments and prediction-error calibration (including abstain-on-low-evidence rules);
DEV4 structural discovery and independent transfer evaluation with no-prior and unrelated-prior control arms and
real held-out task families; DEV5 replay/retention; DEV6 gated integration. Each needs its own review gate.

## Fix history
- **DEV2.1:** the first DEV2 compared only file size before appending, so an external edit that kept the file length
  unchanged was accepted and a new entry was chained onto a corrupted log (found by external testing; `verify()` detected the
  corruption afterwards). Fixed by tracking file identity and a running SHA-256 of all verified bytes, with an optional
  metadata mode. Regression tests edit existing bytes without changing the length, including with the mtime restored.
  The original tests missed this because the only external-write test appended a byte, which changes the size.
