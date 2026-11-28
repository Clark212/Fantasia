import json
import random
import tempfile
from pathlib import Path

from asm import ASMEngine, __version__


BELIEF_SCENARIOS = [
    ("Alex", "door is locked"),
    ("Mina", "box is empty"),
    ("Theo", "lamp is on"),
    ("Sara", "key is inside"),
]

EMOTION_TRAIN = [
    "Maya felt disappointed because the goal failed",
    "Kai felt disappointed because the plan failed",
    "Noah felt relieved because the danger ended",
    "Lina felt relieved because the threat ended",
    "Iris felt frustrated because the attempt failed repeatedly",
    "Omar felt frustrated because the task failed repeatedly",
]
EMOTION_TEST = [
    ("the project failed", "disappointed"),
    ("the mission failed", "disappointed"),
    ("the danger ended", "relieved"),
    ("the threat ended", "relieved"),
    ("the experiment failed repeatedly", "frustrated"),
    ("the build failed repeatedly", "frustrated"),
]

LATENT_TRAIN = [
    "repeated requests increase queue pressure; queue pressure crosses threshold, server fails",
    "repeated charging increases battery heat; battery heat crosses threshold, battery shuts down",
    "repeated traffic increases road pressure; road pressure crosses threshold, traffic flow fails",
]
LATENT_TEST = [
    "repeated computation increases processor temperature; processor temperature crosses threshold, processor fails",
    "repeated pumping increases pipe pressure; pipe pressure crosses threshold, pipe fails",
    "repeated loading increases bridge pressure; bridge pressure crosses threshold, bridge fails",
]


def run(seed: int):
    rng = random.Random(seed)
    with tempfile.TemporaryDirectory() as td:
        asm = ASMEngine(Path(td) / "bench.db")

        # False-belief separation.
        belief_pass = 0
        scenarios = BELIEF_SCENARIOS[:]
        rng.shuffle(scenarios)
        for holder, prop in scenarios:
            asm.process(
                f"{holder} believes that {prop}",
                training=True,
            )
            # Negate the same proposition in world state.
            words = prop.split()
            if "is" in words:
                i = words.index("is")
                neg = " ".join(words[:i+1] + ["not"] + words[i+1:])
            else:
                neg = "not " + prop
            asm.process(f"Actually, {neg}", training=True)

            comp = asm.compare_belief(holder, prop)
            belief_pass += int(
                comp["agent"]["truth"] is True
                and comp["world"]["truth"] is False
            )

        # Revision.
        revision_pass = 0
        for holder, prop in scenarios:
            asm.process(
                f"{holder} believes that {prop}",
                training=True,
            )
            words = prop.split()
            i = words.index("is")
            neg = " ".join(words[:i+1] + ["not"] + words[i+1:])
            asm.process(
                f"{holder} believes that {neg}",
                training=True,
            )
            asm.process(
                f"{holder} believes that {neg}",
                training=True,
            )
            revision_pass += int(
                asm.belief(holder, prop)["truth"] is False
            )

        # Learned emotions.
        training = EMOTION_TRAIN[:]
        rng.shuffle(training)
        for text in training:
            asm.process(text, training=True)

        emotion_pass = 0
        emotion_detail = []
        for query, expected in EMOTION_TEST:
            result = asm.infer_emotion(query)
            got = result[0]["emotion"] if result else None
            emotion_pass += int(got == expected)
            emotion_detail.append({
                "query": query,
                "expected": expected,
                "got": got,
                "pass": got == expected,
            })

        # Self-created concept reuse.
        latent_training = LATENT_TRAIN[:]
        rng.shuffle(latent_training)
        for text in latent_training:
            asm.process(text, training=True)

        promoted = asm.latent_concepts()
        latent_pass = 0
        latent_detail = []
        for query in LATENT_TEST:
            active = asm.expand_problem(query)["latent_concepts"]
            ok = bool(active)
            latent_pass += int(ok)
            latent_detail.append({
                "query": query,
                "active": active[:3],
                "pass": ok,
            })

        result = {
            "seed": seed,
            "belief_separation": belief_pass / len(BELIEF_SCENARIOS),
            "belief_revision": revision_pass / len(BELIEF_SCENARIOS),
            "emotion_transfer": emotion_pass / len(EMOTION_TEST),
            "latent_reactivation": latent_pass / len(LATENT_TEST),
            "emotion_detail": emotion_detail,
            "latent_detail": latent_detail,
            "stats": asm.stats(),
        }
        asm.close()
        return result


runs = [run(seed) for seed in range(10)]

summary = {
    "version": __version__,
    "runs": len(runs),
    "belief_separation_pct": round(
        100 * sum(r["belief_separation"] for r in runs) / len(runs),
        2,
    ),
    "belief_revision_pct": round(
        100 * sum(r["belief_revision"] for r in runs) / len(runs),
        2,
    ),
    "emotion_transfer_pct": round(
        100 * sum(r["emotion_transfer"] for r in runs) / len(runs),
        2,
    ),
    "latent_reactivation_pct": round(
        100 * sum(r["latent_reactivation"] for r in runs) / len(runs),
        2,
    ),
    "runs_detail": runs,
}

out = Path("/mnt/data/ASM_v0.1.1.5_benchmark_summary.json")
out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
print(json.dumps(
    {k: v for k, v in summary.items() if k != "runs_detail"},
    indent=2,
))
print(f"saved: {out}")
