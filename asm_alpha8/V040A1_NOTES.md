# v0.4.0-alpha.1 notes

This release branches from v0.3.0-alpha.12-testfix2. It does not declare the older v0.3 line retroactively stable.

New files/capabilities:
- `asm/planning.py`: bounded internal simulator/planner.
- `tests/test_v040a1.py`: planner invariants and controls.
- `benchmark_v040a1.py`: real learned-mechanism planning gate.

Compatibility fix:
- `ASMEngine.close(save_snapshot=False)` closes all persistence handles without writing a snapshot. This removes the Windows SQLite lock in the legacy migration test while keeping ordinary `close()` behavior unchanged.
