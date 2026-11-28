import json
import random
import tempfile
from pathlib import Path

from asm import ASMEngine, __version__
from asm.attention import AttentionSystem
from asm.config import ASMConfig


NESTED_CASES = [
    (
        "Alice believes Bob believes that the box is full",
        ["Alice", "Bob"],
        "box is full",
        True,
    ),
    (
        "Mina thinks Theo believes that the lamp is on",
        ["Mina", "Theo"],
        "lamp is on",
        True,
    ),
    (
        "Ivy believes Jay thinks that the key is not hidden",
        ["Ivy", "Jay"],
        "key is hidden",
        False,
    ),
    (
        "Ava believes Ben thinks Cara believes that the gate is open",
        ["Ava", "Ben", "Cara"],
        "gate is open",
        True,
    ),
    (
        "Noah thinks Lina believes Omar believes that the token is not valid",
        ["Noah", "Lina", "Omar"],
        "token is valid",
        False,
    ),
]


def run(seed):
    rng = random.Random(seed)

    with tempfile.TemporaryDirectory() as td:
        asm = ASMEngine(Path(td) / "bench.db")

        # 1) Nested mind-state correctness and isolation.
        nested_pass = 0
        nested_rows = []
        cases = NESTED_CASES[:]
        rng.shuffle(cases)

        for text, path, prop, expected in cases:
            asm.process(text, training=True)
            state = asm.nested_belief(path, prop)
            got = state["truth"]
            ok = got is expected
            nested_pass += int(ok)
            nested_rows.append({
                "text": text,
                "path": path,
                "expected": expected,
                "got": got,
                "pass": ok,
            })

        # Direct Bob belief should not overwrite Alice's model of Bob.
        asm.process(
            "Alice believes Bob believes that the door is locked",
            training=True,
        )
        asm.process(
            "Bob believes that the door is not locked",
            training=True,
        )
        nested_isolation = (
            asm.nested_belief(
                ["Alice", "Bob"],
                "door is locked",
            )["truth"] is True
            and asm.belief(
                "Bob",
                "door is locked",
            )["truth"] is False
        )

        # 2) Self-capability revision.
        for _ in range(5):
            asm.report_strategy_outcome(
                "logic",
                "direct_rule",
                True,
            )
        before = asm.capability("logic")["success_probability"]

        for _ in range(10):
            asm.report_strategy_outcome(
                "logic",
                "direct_rule",
                False,
            )
        after = asm.capability("logic")["success_probability"]
        self_revision = before > 0.65 and after < 0.5 and after < before

        # 3) Strategy adaptation.
        for _ in range(6):
            asm.report_strategy_outcome(
                "search",
                "repeat_same_path",
                False,
            )

        # 4) Internal failure signal rises while repeated failure is ongoing.
        frustration_after_failures = (
            asm.self_state()["internal"]["frustration_like"]
        )
        internal_failure_signal = frustration_after_failures > 0.35

        # A successful alternative should become preferred and cool the
        # failure-pressure signal rather than leaving it permanently high.
        for _ in range(3):
            asm.report_strategy_outcome(
                "search",
                "try_alternative",
                True,
            )
        ranked = asm.choose_strategy(
            "search",
            ["repeat_same_path", "try_alternative"],
        )
        strategy_adaptation = (
            bool(ranked)
            and ranked[0]["strategy"] == "try_alternative"
        )
        frustration_after_success = (
            asm.self_state()["internal"]["frustration_like"]
        )
        failure_signal_recovery = (
            frustration_after_success < frustration_after_failures
        )

        # 5) Attention shift under a strong new epicenter.
        attention = AttentionSystem(ASMConfig())
        first = attention.update(
            [("A", 1.0), ("B", 0.15)],
            surprise=0.1,
            magnitude=0.2,
            event_id=1,
        )
        second = attention.update(
            [("Z", 6.0), ("Y", 0.1)],
            surprise=1.0,
            magnitude=1.0,
            event_id=2,
        )
        attention_shift = (
            first["epicenter"] == "A"
            and second["epicenter"] == "Z"
            and second["shifted"]
        )

        result = {
            "seed": seed,
            "nested_belief_accuracy": nested_pass / len(cases),
            "nested_isolation": nested_isolation,
            "self_capability_revision": self_revision,
            "strategy_adaptation": strategy_adaptation,
            "internal_failure_signal": internal_failure_signal,
            "failure_signal_recovery": failure_signal_recovery,
            "attention_shift": attention_shift,
            "nested_cases": nested_rows,
            "capability_before": before,
            "capability_after": after,
            "strategy_ranking": ranked,
            "frustration_after_failures": frustration_after_failures,
            "frustration_after_success": frustration_after_success,
            "stats": asm.stats(),
        }
        asm.close()
        return result


runs = [run(seed) for seed in range(10)]

summary = {
    "version": __version__,
    "runs": len(runs),
    "nested_belief_accuracy_pct": round(
        100 * sum(r["nested_belief_accuracy"] for r in runs) / len(runs),
        2,
    ),
    "nested_isolation_pct": round(
        100 * sum(bool(r["nested_isolation"]) for r in runs) / len(runs),
        2,
    ),
    "self_capability_revision_pct": round(
        100 * sum(bool(r["self_capability_revision"]) for r in runs) / len(runs),
        2,
    ),
    "strategy_adaptation_pct": round(
        100 * sum(bool(r["strategy_adaptation"]) for r in runs) / len(runs),
        2,
    ),
    "internal_failure_signal_pct": round(
        100 * sum(bool(r["internal_failure_signal"]) for r in runs) / len(runs),
        2,
    ),
    "failure_signal_recovery_pct": round(
        100 * sum(bool(r["failure_signal_recovery"]) for r in runs) / len(runs),
        2,
    ),
    "attention_shift_pct": round(
        100 * sum(bool(r["attention_shift"]) for r in runs) / len(runs),
        2,
    ),
    "runs_detail": runs,
}

out = Path("/mnt/data/ASM_v0.1.1.7_benchmark_summary.json")
out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
print(json.dumps(
    {k: v for k, v in summary.items() if k != "runs_detail"},
    indent=2,
))
print(f"saved: {out}")
