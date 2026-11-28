"""Offline, reproducible surface-language training; never runs during ASM use.

The small authored corpus teaches speech-act realization. Validation uses new
slot values/continuous conditions but the same surface grammar. This is NOT a
test of unseen English phrasing or broad language proficiency.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import random
import time

from asm.cognitive_packet import CognitivePacket
from asm.recurrent_writer import ACTIONS, condition, make_model, tokenize

SURFACES = {
    "greeting": ("Hey. What would you like to talk about?", "Hey. What would you like to discuss today?"),
    "wellbeing": ("My internal confidence signal is <confidence> and my curiosity signal is <curiosity>.",
                  "My internal confidence signal is <confidence> and my curiosity signal is <curiosity>. These are computational signals."),
    "identity": ("I'm ASM, a memory-centric AI with a recurrent language interface.",
                 "I'm ASM, a memory-centric AI. My recurrent language interface describes my structured memory and self-model."),
    "gratitude": ("You're welcome.", "You're welcome. What would you like to discuss next?"),
    "farewell": ("See you.", "See you. You can continue later."),
    "negative_affect": ("You sound upset. What happened?", "You sound upset. Can you tell me what happened?"),
    "positive_affect": ("What happened? Tell me more.", "Tell me more about what happened."),
    "uncertainty": ("I don't know enough to answer that.", "I don't have enough reliable information to answer that yet."),
    "confusion": ("I'm not sure what you mean.", "I'm not sure what you mean. Can you explain?"),
    "stored": ("Got it. I'll remember that.", "Got it. I'll keep that in long-term memory."),
    "listening": ("Go on.", "Go on. What would you like to discuss?"),
    "belief_report": ("<claim>", "Here is the stored belief report: <claim>"),
    "memory_report": ("I remember this report: <claim>", "I remember this reported event: <claim>"),
    "previous_message": ("Your previous message was: <claim>", "Here is your previous message: <claim>"),
    "cognitive_report": ("<claim>", "Understood. <claim>"),
}


def examples(seed, count):
    rng = random.Random(seed)
    rows = []
    for _ in range(count):
        for action in ACTIONS:
            for style in ("brief", "full"):
                surface = SURFACES[action][int(style == "full")]
                slots = {t[1:-1]: f"new content {rng.randrange(10000000)}"
                         for t in tokenize(surface) if t.startswith("<")}
                rows.append((CognitivePacket(action, slots, uncertainty=rng.random(), style=style), surface))
    rng.shuffle(rows)
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--epochs", type=int, default=180)
    args = parser.parse_args()
    import torch
    torch.set_num_threads(1)
    torch.manual_seed(240925)
    start = time.perf_counter()
    train, validation = examples(1107, 8), examples(71011, 3)
    vocab = ["<pad>", "<bos>", "<eos>"] + sorted({t for _, s in train for t in tokenize(s)})
    ids = {w: i for i, w in enumerate(vocab)}

    def batch(rows):
        sequences = [[ids["<bos>"]] + [ids[t] for t in tokenize(s)] + [ids["<eos>"]] for _, s in rows]
        n = max(map(len, sequences))
        data = torch.tensor([s + [0] * (n - len(s)) for s in sequences])
        return data[:, :-1], data[:, 1:], torch.tensor([condition(p) for p, _ in rows])

    x, y, c = batch(train)
    xv, yv, cv = batch(validation)
    model = make_model(len(vocab))
    opt = torch.optim.Adam(model.parameters(), lr=.006)
    loss_fn = torch.nn.CrossEntropyLoss(ignore_index=0)
    for epoch in range(args.epochs):
        model.train()
        order = torch.randperm(len(train))
        losses = []
        for idx in order.split(60):
            opt.zero_grad()
            logits, _ = model(x[idx], c[idx])
            loss = loss_fn(logits.reshape(-1, len(vocab)), y[idx].reshape(-1))
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.)
            opt.step()
            losses.append(float(loss.detach()))
        if (epoch + 1) % 30 == 0:
            print(f"epoch={epoch+1} loss={sum(losses)/len(losses):.6f}", flush=True)
    model.eval()
    with torch.inference_mode():
        logits, _ = model(xv, cv)
        mask = yv.ne(0)
        token_acc = float(logits.argmax(-1)[mask].eq(yv[mask]).float().mean())
    path = Path(__file__).parent / "asm/data/recurrent_writer_v020a5.pt"
    torch.save(model.state_dict(), path)
    meta = {"format": "asm-conditioned-gru-writer-v1", "seed": 240925, "vocab": vocab,
            "embedding_dim": 40, "hidden_dim": 80, "parameters": sum(p.numel() for p in model.parameters()),
            "checkpoint_bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "training_examples": len(train), "validation_examples": len(validation),
            "validation_teacher_forced_token_accuracy": token_acc,
            "validation_scope": "new opaque content and numeric conditions, same authored surface grammar",
            "training_seconds": time.perf_counter() - start, "frozen_at_runtime": True,
            "attention_free": True}
    path.with_suffix(".json").write_text(json.dumps(meta, indent=2))
    data_dir = Path(__file__).parent / "data"
    for name, rows in [("writer_train.jsonl", train), ("writer_validation.jsonl", validation)]:
        (data_dir / name).write_text("\n".join(json.dumps({"packet": p.as_dict(), "target": s}) for p, s in rows) + "\n")
    print(json.dumps({k:v for k,v in meta.items() if k != "vocab"}, indent=2))


if __name__ == "__main__":
    main()
