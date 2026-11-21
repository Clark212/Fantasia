import csv
import hashlib
import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path

from asm.learning import Experience, ExperienceStore
from asm.learning.persistence import (GENESIS_HASH, SCHEMA_VERSION, ExperienceLog,
                                      LogCorruptionError, audit_leakage)


def rec(i, *, task=None, status="labeled", source="dataset", obs=None, out=None):
    return Experience(f"e{i}", source, "math", task or f"task-{i % 5}", obs or {"x": i},
                      None, out or {"y": i * 2}, status, 1.0, {})


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.path = self.dir / "sub" / "log.jsonl"

    def tearDown(self):
        self._tmp.cleanup()

    def filled(self, n=6, **kw):
        log = ExperienceLog(self.path, fsync=False, **kw)
        for i in range(n):
            self.assertTrue(log.append(rec(i)))
        return log


class RoundTripTests(Base):
    def test_persist_reload_and_dedupe_across_reopen(self):
        log = self.filled()
        head = log.head_hash
        again = ExperienceLog(self.path, fsync=False)
        self.assertEqual((len(again), again.head_hash), (6, head))
        self.assertEqual([r.experience_id for r in again.records()], [f"e{i}" for i in range(6)])
        self.assertFalse(again.append(rec(3)))                         # same id
        self.assertFalse(again.append(rec(99, obs={"x": 3}, out={"y": 6}, task="task-3")))  # same fingerprint
        self.assertEqual(again.duplicates, 2)
        self.assertEqual(len(again), 6)

    def test_reloaded_fingerprints_match_originals(self):
        log = self.filled(4)
        self.assertEqual([r.fingerprint for r in log.records()], [rec(i).fingerprint for i in range(4)])

    def test_identical_inputs_give_identical_head_hash(self):
        a = self.filled()
        other = ExperienceLog(self.dir / "other.jsonl", fsync=False)
        for i in range(6):
            other.append(rec(i))
        self.assertEqual(a.head_hash, other.head_hash)
        self.assertNotEqual(a.head_hash, GENESIS_HASH)

    def test_empty_log_verifies(self):
        log = ExperienceLog(self.path, fsync=False)
        self.assertEqual(log.verify(), {"ok": True, "entries": 0, "head_hash": GENESIS_HASH, "errors": []})

    def test_rejects_non_experience(self):
        with self.assertRaises(TypeError):
            ExperienceLog(self.path, fsync=False).append({"experience_id": "x"})


class TamperTests(Base):
    def lines(self):
        return self.path.read_bytes().split(b"\n")[:-1]

    def write(self, lines):
        self.path.write_bytes(b"\n".join(lines) + b"\n")

    def test_edited_record_detected(self):
        self.filled()
        lines = self.lines()
        entry = json.loads(lines[2]); entry["record"]["outcome"] = {"y": 999}
        lines[2] = json.dumps(entry, sort_keys=True, separators=(",", ":")).encode()
        self.write(lines)
        with self.assertRaises(LogCorruptionError):
            ExperienceLog(self.path, fsync=False)

    def test_deleted_middle_entry_detected(self):
        self.filled()
        lines = self.lines(); del lines[2]; self.write(lines)
        with self.assertRaisesRegex(LogCorruptionError, "sequence gap"):
            ExperienceLog(self.path, fsync=False)

    def test_reordered_entries_detected(self):
        self.filled()
        lines = self.lines(); lines[1], lines[2] = lines[2], lines[1]; self.write(lines)
        with self.assertRaisesRegex(LogCorruptionError, "sequence gap"):
            ExperienceLog(self.path, fsync=False)

    def test_entry_spliced_from_another_log_detected_as_prev_mismatch(self):
        self.filled(4)
        other = ExperienceLog(self.dir / "other.jsonl", fsync=False)
        for i in range(4):
            other.append(rec(i + 100))
        mine = self.lines()
        theirs = (self.dir / "other.jsonl").read_bytes().split(b"\n")[:-1]
        mine[2] = theirs[2]            # same seq number, different history
        self.write(mine)
        with self.assertRaisesRegex(LogCorruptionError, "previous-hash mismatch"):
            ExperienceLog(self.path, fsync=False)

    def test_verify_reports_without_raising_and_corrupt_log_refuses_append(self):
        log = self.filled()
        lines = self.lines(); lines[-1] = lines[-1].replace(b'"y":10', b'"y":11'); self.write(lines)
        report = log.verify()
        self.assertFalse(report["ok"]); self.assertTrue(report["errors"])

    def test_external_write_between_appends_refused_before_anything_is_written(self):
        for mode in ("full", "metadata"):
            with self.subTest(mode=mode):
                self.path = self.dir / f"ext-{mode}.jsonl"
                log = self.filled(3, integrity=mode)
                with self.path.open("ab") as stream:
                    stream.write(b"x")
                after_tamper = self.path.read_bytes()
                with self.assertRaisesRegex(LogCorruptionError, "size changed"):
                    log.append(rec(50))
                self.assertEqual(self.path.read_bytes(), after_tamper)   # refused BEFORE writing, not after

    def test_truncated_file_refused_before_anything_is_written(self):
        for mode in ("full", "metadata"):
            with self.subTest(mode=mode):
                self.path = self.dir / f"trunc-{mode}.jsonl"
                log = self.filled(4, integrity=mode)
                raw = self.path.read_bytes()
                self.path.write_bytes(raw[:-5])
                with self.assertRaisesRegex(LogCorruptionError, "size changed"):
                    log.append(rec(51))
                self.assertEqual(self.path.read_bytes(), raw[:-5])

    def test_newer_schema_rejected_with_clear_message(self):
        self.filled(2)
        lines = self.lines()
        entry = json.loads(lines[1]); entry["schema"] = SCHEMA_VERSION + 1
        lines[1] = json.dumps(entry).encode(); self.write(lines)
        with self.assertRaisesRegex(LogCorruptionError, "newer version"):
            ExperienceLog(self.path, fsync=False)


class TornTailTests(Base):
    def test_torn_tail_refused_by_default_and_repaired_on_request(self):
        log = self.filled(4)
        head = log.head_hash
        with self.path.open("ab") as stream:
            stream.write(b'{"schema":1,"seq":5,"pr')
        with self.assertRaises(LogCorruptionError):
            ExperienceLog(self.path, fsync=False)
        fixed = ExperienceLog(self.path, fsync=False, repair_torn_tail=True)
        self.assertGreater(fixed.repaired_bytes, 0)
        self.assertEqual((len(fixed), fixed.head_hash), (4, head))
        self.assertTrue(fixed.append(rec(10)))
        self.assertTrue(ExperienceLog(self.path, fsync=False).verify()["ok"])

    def test_repair_never_hides_a_corrupt_complete_entry(self):
        self.filled(4)
        lines = self.path.read_bytes().split(b"\n")[:-1]
        lines[1] = lines[1].replace(b'"y":2', b'"y":3')
        self.path.write_bytes(b"\n".join(lines) + b"\n")
        with self.assertRaises(LogCorruptionError):
            ExperienceLog(self.path, fsync=False, repair_torn_tail=True)


class ExternalChangeTests(Base):
    """Regression: an external edit that keeps the file LENGTH unchanged must be refused."""

    MODES = ("full", "metadata")

    def edit_same_length(self, restore_times=False):
        before = self.path.stat()
        raw = self.path.read_bytes()
        marker = b'"y":4'                      # record e2: outcome y=4
        self.assertIn(marker, raw)
        edited = raw.replace(marker, b'"y":5', 1)
        self.assertEqual(len(edited), len(raw))
        self.path.write_bytes(edited)
        if restore_times:
            os.utime(self.path, ns=(before.st_atime_ns, before.st_mtime_ns))
        return edited

    def assertRefusedAndUntouched(self, log, edited):
        with self.assertRaisesRegex(LogCorruptionError, "outside this writer|changed|identity|missing"):
            log.append(rec(500))
        self.assertEqual(self.path.read_bytes(), edited)      # nothing was appended
        self.assertEqual(len(log), 6)
        with self.assertRaises(LogCorruptionError):           # still refused, not a one-shot
            log.append(rec(501))
        self.assertFalse(log.verify()["ok"])

    def test_same_length_edit_then_append_is_refused_in_every_mode(self):
        for mode in self.MODES:
            with self.subTest(mode=mode):
                self.path = self.dir / f"{mode}.jsonl"
                log = self.filled(integrity=mode)
                self.assertRefusedAndUntouched(log, self.edit_same_length())

    def test_same_length_edit_with_restored_mtime_is_refused_in_full_mode(self):
        log = self.filled(integrity="full")
        self.assertRefusedAndUntouched(log, self.edit_same_length(restore_times=True))

    @unittest.skipIf(sys.platform == "win32", "ctime is creation time on Windows; use integrity='full'")
    def test_metadata_mode_catches_restored_mtime_through_ctime(self):
        import time
        log = self.filled(integrity="metadata")
        time.sleep(0.05)                       # move past the filesystem timestamp granularity of our last write
        edited = self.edit_same_length(restore_times=True)   # same length, mtime put back; ctime still moves
        self.assertRefusedAndUntouched(log, edited)

    def test_metadata_mode_tail_check_catches_same_tick_edit_of_last_entry(self):
        # Simulate a timestamp-granularity collision: the edit leaves mtime/ctime equal to the snapshot.
        log = self.filled(integrity="metadata")
        raw = self.path.read_bytes()
        edited = raw.replace(b'"y":10', b'"y":19', 1)           # last entry (e5), same length
        self.assertEqual(len(edited), len(raw)); self.assertNotEqual(edited, raw)
        self.path.write_bytes(edited)
        log._remember_stat(os.stat(self.path))                  # make the metadata look unchanged
        with self.assertRaisesRegex(LogCorruptionError, "last entry changed"):
            log.append(rec(70))
        self.assertEqual(self.path.read_bytes(), edited)

    def test_metadata_mode_known_limit_older_entry_edit_inside_timestamp_tick(self):
        # Documents the opt-in mode's residual risk (see module docstring). If this ever starts
        # failing the guard got stronger: update the docstring and ALPHA8_DEV2 notes.
        log = self.filled(integrity="metadata")
        self.edit_same_length()                                 # older entry e2
        log._remember_stat(os.stat(self.path))                  # simulate identical timestamps
        self.assertTrue(log.append(rec(71)))                    # accepted by the O(1) mode ...
        self.assertFalse(log.verify()["ok"])                    # ... but verify()/reopen still catch it

    def test_opening_an_existing_log_does_not_touch_its_timestamps(self):
        self.filled(3)
        before = self.path.stat()
        ExperienceLog(self.path, fsync=False)
        after = self.path.stat()
        self.assertEqual((before.st_mtime_ns, before.st_size), (after.st_mtime_ns, after.st_size))

    def test_default_mode_is_full(self):
        log = ExperienceLog(self.path, fsync=False)
        self.assertEqual(log.integrity, "full")
        with self.assertRaises(ValueError):
            ExperienceLog(self.dir / "x.jsonl", integrity="sometimes")

    def test_replaced_file_identity_is_refused_even_with_identical_bytes(self):
        log = self.filled()
        copy = self.path.with_suffix(".copy")
        copy.write_bytes(self.path.read_bytes())
        os.replace(copy, self.path)            # new inode, byte-identical content
        for mode in self.MODES:
            log._integrity = mode
            with self.assertRaisesRegex(LogCorruptionError, "identity"):
                log.append(rec(600))

    def test_deleted_file_is_refused(self):
        log = self.filled()
        self.path.unlink()
        with self.assertRaisesRegex(LogCorruptionError, "missing"):
            log.append(rec(700))

    def test_check_external_changes_is_public_and_accurate(self):
        log = self.filled()
        self.assertTrue(log.check_external_changes())
        self.edit_same_length()
        with self.assertRaises(LogCorruptionError):
            log.check_external_changes()

    def test_own_appends_and_batches_never_trip_the_guard(self):
        for mode in self.MODES:
            with self.subTest(mode=mode):
                log = ExperienceLog(self.dir / f"own-{mode}.jsonl", fsync=False, integrity=mode)
                for i in range(30):
                    self.assertTrue(log.append(rec(i)))
                self.assertEqual(log.append_many(rec(i) for i in range(30, 60)), {"added": 30, "duplicates": 0})
                self.assertTrue(log.check_external_changes())
                self.assertTrue(ExperienceLog(self.dir / f"own-{mode}.jsonl", fsync=False).verify()["ok"])

    def test_batch_is_refused_before_writing_anything_when_log_was_edited(self):
        log = self.filled()
        edited = self.edit_same_length()
        with self.assertRaises(LogCorruptionError):
            log.append_many(rec(i) for i in range(800, 810))
        self.assertEqual(self.path.read_bytes(), edited)

    def test_repair_then_append_keeps_guard_consistent(self):
        self.filled(3)
        with self.path.open("ab") as stream:
            stream.write(b'{"schema":1,"seq":4')
        log = ExperienceLog(self.path, fsync=False, repair_torn_tail=True)
        self.assertTrue(log.append(rec(9)))
        self.assertTrue(log.check_external_changes())
        self.assertTrue(ExperienceLog(self.path, fsync=False).verify()["ok"])


class ImportAndStoreTests(Base):
    def test_import_jsonl_with_legacy_outcome_field_and_dedupe(self):
        src = self.dir / "d.jsonl"
        rows = [{"experience_id": f"j{i}", "domain": "math", "task_id": "t", "observation": {"x": i},
                 "actual_outcome": {"y": i}} for i in range(3)]
        src.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
        log = ExperienceLog(self.path, fsync=False)
        self.assertEqual(log.import_file(src), {"added": 3, "duplicates": 0})
        self.assertEqual(log.import_file(src), {"added": 0, "duplicates": 3})
        self.assertEqual(next(log.records()).outcome, {"y": 0})

    def test_import_csv(self):
        src = self.dir / "d.csv"
        with src.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["experience_id", "domain", "task_id", "observation", "outcome"])
            w.writeheader()
            w.writerow({"experience_id": "c1", "domain": "math", "task_id": "t", "observation": '{"x":1}', "outcome": '{"y":2}'})
        log = ExperienceLog(self.path, fsync=False)
        self.assertEqual(log.import_file(src)["added"], 1)

    def test_bad_row_stops_import_but_keeps_earlier_rows_valid(self):
        src = self.dir / "bad.jsonl"
        good = {"experience_id": "g", "domain": "math", "task_id": "t", "observation": {"x": 1}}
        src.write_text(json.dumps(good) + "\n" + json.dumps({"experience_id": "b"}) + "\n")
        log = ExperienceLog(self.path, fsync=False)
        with self.assertRaises(ValueError):
            log.import_file(src)
        self.assertEqual(len(log), 1)
        self.assertTrue(log.verify()["ok"])

    def test_load_into_store_respects_capacity(self):
        log = self.filled(3)
        store = ExperienceStore(capacity=2)
        self.assertEqual(log.load_into(store), 3)
        self.assertEqual((len(store), store.dropped_oldest), (2, 1))


class ConcurrencyTests(Base):
    def test_threads_append_without_corrupting_chain(self):
        log = ExperienceLog(self.path, fsync=False)
        def work(base):
            for i in range(25):
                log.append(rec(base * 100 + i))
        threads = [threading.Thread(target=work, args=(b,)) for b in range(8)]
        [t.start() for t in threads]; [t.join() for t in threads]
        self.assertEqual(len(log), 200)
        report = ExperienceLog(self.path, fsync=False).verify()
        self.assertTrue(report["ok"]); self.assertEqual(report["entries"], 200)


class ManifestAndAuditTests(Base):
    def test_manifest_counts_and_file_hash(self):
        log = ExperienceLog(self.path, fsync=False)
        log.append(rec(1)); log.append(rec(2, status="generated")); log.append(rec(3, status="inferred"))
        m = log.write_manifest(self.dir / "manifest.json")
        self.assertEqual((m["entries"], m["independent_evidence"], m["generated_or_inferred"]), (3, 1, 2))
        self.assertEqual(m["file_sha256"], hashlib.sha256(self.path.read_bytes()).hexdigest())
        self.assertEqual(m["head_hash"], log.head_hash)
        self.assertEqual(json.loads((self.dir / "manifest.json").read_text())["entries"], 3)
        self.assertIn("clean", m["leakage_audit"])

    def test_stable_group_split_is_clean(self):
        log = ExperienceLog(self.path, fsync=False)
        for i in range(60):
            log.append(rec(i, obs={"x": i}))
        audit = log.manifest()["leakage_audit"]
        self.assertEqual(audit["task_overlap"], 0)
        self.assertEqual(audit["fingerprint_overlap"], 0)

    def test_audit_detects_planted_leaks(self):
        train = [rec(1, task="A"), rec(2, task="B")]
        test = [rec(3, task="A"),                                    # task A in both
                rec(4, task="C", obs={"x": 2}, out={"y": 0}),        # train input reused, different outcome
                rec(5, task="D", status="generated")]                # weak evidence in evaluation
        a = audit_leakage({"train": train, "validation": [], "test": test})
        self.assertFalse(a["clean"])
        self.assertEqual(a["task_overlap"], 1)
        self.assertEqual(a["train_eval_observation_overlap"], 1)
        self.assertEqual(a["weak_evidence_in_evaluation"], 1)

    def test_audit_detects_duplicate_fingerprint_across_splits(self):
        a = audit_leakage({"train": [rec(1)], "validation": [], "test": [rec(77, obs={"x": 1}, out={"y": 2}, task="task-1")]})
        self.assertEqual(a["fingerprint_overlap"], 1)

    def test_audit_clean_case(self):
        a = audit_leakage({"train": [rec(1, task="A")], "validation": [], "test": [rec(2, task="B")]})
        self.assertTrue(a["clean"])


if __name__ == "__main__":
    unittest.main()
