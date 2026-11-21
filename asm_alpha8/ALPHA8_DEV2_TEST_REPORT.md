# Alpha 8 DEV2.1 Test Report

**Artifact:** `ASM_alpha8_DEV2_fix1.zip` (parent: `ASM_alpha8_DEV1.zip`; supersedes the first `ASM_alpha8_DEV2.zip`).
Development prototype; not an official release.

## Defect fixed in this revision
First DEV2 checked only file size before appending; a same-length in-place edit was accepted (reproduced: old code
`append ACCEPTED=True`, file grew, `verify()` then failed). Fixed code refuses before writing and leaves the file untouched.

## Verified
- Persistence tests: **38 passed** (up from 24), stable over repeated runs. New: same-length edit in both integrity modes,
  same-length edit with restored mtime (full mode, and metadata mode via ctime on POSIX), refusal before any write
  (asserted by byte comparison), truncation, appended bytes, file replacement with identical bytes, deletion, public
  `check_external_changes()`, own appends/batches never tripping the guard, batch refused before writing, repair then append,
  opening an existing log not touching its timestamps, metadata-mode tail check, and the pinned metadata-mode limit.
- Targeted run with DEV1 (20) and 7.9 compatibility (14) tests: **72 passed**.
- Non-torch regression subset: **454 passed, 57 failed, 1 skipped** (454 = 396 baseline + 20 DEV1 + 38 DEV2). The 57 failures
  are the same count as the 7.9 baseline run without PyTorch, attributed to PyTorch being unavailable in the sandbox.
- Mutation checks, each making tests fail: skipping the full-content digest compare, the identity check, the size check,
  ctime in metadata mode, hashing of own writes, and the last-entry check; plus the earlier hash / sequence / previous-hash /
  dedupe mutations. Two guard mutations (size check, last-entry check) initially survived and led to stronger assertions.
- Performance (one machine, 20,000 entries, 7.9 MB): append_many 20k ~1.0 s; single append ~6.8 ms (full) vs ~0.06 ms
  (metadata); reopen with full chain verification ~0.7 s.

## Not verified
- The 3 torch-dependent test files and the 57 torch-related failures were not run with PyTorch.
- No multi-process writer or crash-injection testing beyond a simulated torn tail.
- Timestamp-granularity collisions are simulated by resetting stored metadata, not produced on real filesystems.
- Windows behavior (ctime semantics) is documented but not tested.
- No claim of improved intelligence, transfer, or Alpha 8 completion.
