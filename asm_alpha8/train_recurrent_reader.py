from __future__ import annotations

import json
import random
from pathlib import Path

import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from asm.recurrent_reader import LABELS, _CharGRUModel

ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "asm" / "data"
OUT_DIR.mkdir(parents=True, exist_ok=True)

SEED = 20260924
random.seed(SEED)
torch.manual_seed(SEED)
torch.set_num_threads(2)

NAMES = [
    "Alice", "Ben", "Cara", "Dan", "Evan", "Fiona", "Gina", "Hugo",
    "Iris", "Kai", "Lina", "Mina", "Noah", "Omar", "Theo", "Vera",
    "Nova", "Mira", "Leo", "Ava",
]
PROPS = [
    "the gate is open", "the route is safe", "the lamp is on", "the key is hidden",
    "the project succeeds", "the mission succeeds", "the storm continues",
    "the danger remains", "the token is valid", "the box is empty",
]
STRATEGIES = ["analogy", "simulation", "search", "decomposition", "recheck", "planning"]

TEMPLATES = {
    "belief": [
        "{a} believes that {p}", "{a} thinks {p}", "{a} assumes {p}",
        "{a} figures {p}", "{a} is convinced {p}", "{a} is sure {p}",
        "{a} learned that {p}", "{a} realized {p}", "{a} reckons {p}",
        "{a} is certain {p}", "{a} discovered that {p}", "{a} found out {p}",
    ],
    "nested_belief": [
        "{a} believes {b} thinks {p}", "{a} suspects {b} believes {p}",
        "{a} is convinced {b} thinks {p}", "{a} has the impression {b} assumes {p}",
        "{a} figures {b} expects {p}", "{a} is sure {b} thinks {p}",
        "{a} reckons {b} thinks {p}", "{a} is certain {b} believes {p}",
        "{a} believes {b} thinks {c} believes {p}",
    ],
    "drive": [
        "{a} wants {p}", "{a} hopes {p}", "{a} hoped {p}",
        "{a} had been hoping {p}", "{a} desperately hoped for success",
        "{a} wishes {p}", "{a} aims to succeed", "{a} has been hoping {p}",
    ],
    "drive_fear_source": [
        "{a} fears {p}", "{a} worried that {p}", "{a} was scared {p}",
        "{a} had been afraid {p}", "{a} is fearful that {p}", "{a} is afraid {p}",
    ],
    "drive_expectation_source": [
        "{a} expects {p}", "{a} predicted {p}", "{a} anticipates {p}",
        "{a} expected that {p}", "{a} predicted that {p}", "{a} anticipated that {p}",
    ],
    "self_outcome": [
        "I tried {s} and it worked", "I used {s} and it succeeded",
        "my {s} strategy worked successfully", "{s} worked successfully",
        "I tested {s} and it passed", "I chose {s} and it solved the problem",
        "I ran {s} and it succeeded",
    ],
    "self_outcome_failure_source": [
        "I tried {s} and it failed", "I used {s} and it failed again",
        "my {s} strategy failed", "{s} failed", "I tested {s} and it did not work",
        "I chose {s} and it was wrong", "I ran {s} and it failed",
    ],
    "other": [
        "pressure increases temperature", "practice improves skill", "the server stores data",
        "a blue object sits beside the table", "what time is the meeting",
        "the circuit links current", "the box contains an item", "rain fell during the night",
        "the program reads a file", "the sensor reports voltage", "the queue became longer",
        "please summarize the result", "this sentence has no mental state",
    ],
}

# Templates deliberately held out from training to make validation less friendly.
HELD_OUT = {
    "belief": ["{a} firmly reckons that {p}", "{a} eventually found out that {p}"],
    "nested_belief": ["{a} now reckons {b} thinks {p}", "{a} remains certain {b} believes {p}"],
    "drive": ["{a} has really been hoping that {p}"],
    "drive_fear_source": ["{a} is still afraid that {p}"],
    "drive_expectation_source": ["{a} had anticipated that {p}"],
    "self_outcome": ["after retrying I ran {s} and it succeeded"],
    "self_outcome_failure_source": ["after retrying I ran {s} and it failed"],
    "other": ["the processor became unusually warm", "a document is still inside the cabinet"],
}

CHARS = list("abcdefghijklmnopqrstuvwxyz0123456789 _-'.,!?;:+/()")
CHAR_TO_ID = {ch: i + 1 for i, ch in enumerate(CHARS)}
MAX_CHARS = 112


def fill(template: str) -> str:
    a, b, c = random.sample(NAMES, 3)
    return template.format(a=a, b=b, c=c, p=random.choice(PROPS), s=random.choice(STRATEGIES))


def make_rows(templates, per_bucket: int):
    rows = []
    label_map = {
        "drive_fear_source": "drive",
        "drive_expectation_source": "drive",
        "self_outcome_failure_source": "self_outcome",
    }
    for source_label, patterns in templates.items():
        label = label_map.get(source_label, source_label)
        for _ in range(per_bucket):
            text = fill(random.choice(patterns))
            if random.random() < 0.3:
                text += random.choice([".", "!", ""])
            if random.random() < 0.15:
                text = text.replace(" ", "  ", 1)
            rows.append((text, label))
    random.shuffle(rows)
    return rows


def encode(text: str):
    text = " ".join(text.lower().replace("’", "'").split())[:MAX_CHARS]
    ids = [CHAR_TO_ID.get(ch, 0) for ch in text]
    ids = ids + [0] * (MAX_CHARS - len(ids))
    return ids


train_rows = make_rows(TEMPLATES, 140)
val_rows = make_rows(HELD_OUT, 40)
label_to_id = {label: i for i, label in enumerate(LABELS)}

x_train = torch.tensor([encode(t) for t, _ in train_rows], dtype=torch.long)
y_train = torch.tensor([label_to_id[l] for _, l in train_rows], dtype=torch.long)
x_val = torch.tensor([encode(t) for t, _ in val_rows], dtype=torch.long)
y_val = torch.tensor([label_to_id[l] for _, l in val_rows], dtype=torch.long)

holder = _CharGRUModel(
    vocab_size=len(CHARS) + 1,
    embedding_dim=20,
    hidden_dim=48,
    num_labels=len(LABELS),
    bidirectional=True,
)
model = holder.model
optimizer = torch.optim.AdamW(model.parameters(), lr=2.5e-3, weight_decay=1e-4)
criterion = nn.CrossEntropyLoss()
loader = DataLoader(TensorDataset(x_train, y_train), batch_size=96, shuffle=True)

best_acc = 0.0
best_state = None
for epoch in range(12):
    model.train()
    for xb, yb in loader:
        optimizer.zero_grad(set_to_none=True)
        logits, _ = model(xb)
        loss = criterion(logits, yb)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()

    model.eval()
    with torch.inference_mode():
        logits, _ = model(x_val)
        pred = logits.argmax(dim=-1)
        acc = float((pred == y_val).float().mean().item())
    print(f"epoch={epoch+1:02d} validation_accuracy={acc:.4f}")
    if acc > best_acc:
        best_acc = acc
        best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}

if best_state is None:
    raise RuntimeError("training produced no model")

weights_path = OUT_DIR / "recurrent_reader_v020a2.pt"
torch.save(best_state, weights_path)
meta = {
    "format": "asm-recurrent-reader-v1",
    "seed": SEED,
    "labels": list(LABELS),
    "chars": CHARS,
    "max_chars": MAX_CHARS,
    "embedding_dim": 20,
    "hidden_dim": 48,
    "bidirectional": True,
    "training_examples": len(train_rows),
    "validation_examples": len(val_rows),
    "validation_accuracy": best_acc,
    "attention_free": True,
    "frozen_at_runtime": True,
}
(OUT_DIR / "recurrent_reader_v020a2.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
print(json.dumps(meta, indent=2))
