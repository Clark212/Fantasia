from __future__ import annotations

import json
import random
from pathlib import Path

import torch
from torch import nn

from asm.encoder import ConceptEncoder
from asm.recurrent_reader import FrozenRecurrentLanguageCore

ROOT=Path(__file__).resolve().parent
DATA=ROOT/"asm"/"data"

SEED=20260924
random.seed(SEED)
torch.manual_seed(SEED)
torch.set_num_threads(2)

core=FrozenRecurrentLanguageCore(
    ConceptEncoder(),
    model_path=DATA/"recurrent_reader_v020a2.pt",
    metadata_path=DATA/"recurrent_reader_v020a2.json",
    min_intent_confidence=0.0,
    min_validation_accuracy=0.0,
)

SOCIAL=[
    "hi","hello","hey","yo","sup","hiya","good morning","good afternoon","good evening",
    "how are you","how's it going","how have you been","what's up","you good","are you okay",
    "thanks","thank you","thanks a lot","cool","nice","lol","bro","okay bro","bye","goodbye",
    "see you","good night","nice to meet you","im angry at u","i am angry at you",
    "im kinda mad at you","im happy today","i feel annoyed","i feel great today",
    "you are funny","that was cool","haha nice","wassup","hey bro","yo dude",
]
NONSOCIAL=[
    "pressure increases temperature","practice improves skill","the server stores data",
    "the circuit links current","the program reads a file","the sensor reports voltage",
    "Alice believes the gate is open","Mina thinks the lamp is on",
    "Alice suspects Bob thinks the key is hidden","Kai believes Mia thinks the route is safe",
    "Evan wants the mission to succeed","Gina fears the storm will continue",
    "Noah expects the token is valid","I tried analogy and it failed",
    "simulation worked successfully","my search strategy failed again",
    "please summarize the result","what causes the server to fail",
    "the battery became hot","the file is inside the cabinet",
    "buhh hole","random words here","purple banana engine","unknown short phrase",
    "the project failed yesterday","the route is safe","the box contains an item",
]
HELD_SOCIAL=[
    "hey there","how u doing","thx","im annoyed with you","night bro","morning","lol okay",
    "nice one","see ya","you alright","im pretty happy rn","hello there","yo man",
    "thanks bro","how you doing today",
]
HELD_NON=[
    "training raises ability","the motor overheated","Lina assumes the key is hidden",
    "Ava wants the project to work","I used decomposition and it failed",
    "strange phrase qzx","blue widget on table","why did the circuit fail",
    "the document remained in storage","Mia expects the route to close",
    "the program crashed twice","study improves knowledge","signal triggers alarm",
]

def augment(s):
    out=s
    if random.random()<0.30: out+=random.choice([".","!","?",""])
    if random.random()<0.15: out=out.replace(" ","  ",1)
    return out

def embedding(text):
    return core._predict(text)[1]

train=[(augment(random.choice(SOCIAL)),1) for _ in range(1400)]
train += [(augment(random.choice(NONSOCIAL)),0) for _ in range(1400)]
val=[(augment(random.choice(HELD_SOCIAL)),1) for _ in range(400)]
val += [(augment(random.choice(HELD_NON)),0) for _ in range(400)]
random.shuffle(train); random.shuffle(val)

x=torch.tensor([embedding(t) for t,_ in train],dtype=torch.float32)
y=torch.tensor([v for _,v in train],dtype=torch.long)
xv=torch.tensor([embedding(t) for t,_ in val],dtype=torch.float32)
yv=torch.tensor([v for _,v in val],dtype=torch.long)

model=nn.Sequential(
    nn.Linear(x.shape[1],32),
    nn.Tanh(),
    nn.Linear(32,2),
)
opt=torch.optim.AdamW(model.parameters(),lr=6e-3,weight_decay=2e-4)

best_metric=-1.0
best_state=None
best_stats=None
thresholds=[0.90,0.95,0.98,0.99,0.995,0.999]

for epoch in range(50):
    order=torch.randperm(len(x))
    model.train()
    for start in range(0,len(x),128):
        idx=order[start:start+128]
        logits=model(x[idx])
        loss=nn.functional.cross_entropy(logits,y[idx])
        opt.zero_grad(set_to_none=True)
        loss.backward()
        opt.step()

    model.eval()
    with torch.inference_mode():
        probs=torch.softmax(model(xv),dim=-1)[:,1]
        pred=(probs>=0.5).long()
        overall=float((pred==yv).float().mean().item())
        stats=[]
        for th in thresholds:
            selected=probs>=th
            tp=int(((yv==1)&selected).sum().item())
            fp=int(((yv==0)&selected).sum().item())
            fn=int(((yv==1)&(~selected)).sum().item())
            precision=tp/max(1,tp+fp)
            recall=tp/max(1,tp+fn)
            stats.append((th,precision,recall,tp+fp))
        # Prefer the highest-coverage threshold with at least 98% precision.
        viable=[s for s in stats if s[1]>=0.98 and s[3]>=20]
        chosen=max(viable,key=lambda s:(s[2],s[3])) if viable else max(stats,key=lambda s:s[1])
        metric=chosen[1]*0.7+chosen[2]*0.3
    if metric>best_metric:
        best_metric=metric
        best_state={k:v.detach().cpu().clone() for k,v in model.state_dict().items()}
        best_stats={"overall_accuracy":overall,"threshold":chosen[0],"precision":chosen[1],"recall":chosen[2],"selected":chosen[3]}

if best_state is None:
    raise RuntimeError("social probe training failed")

torch.save(best_state,DATA/"social_probe_v020a3.pt")
meta={
    "format":"asm-social-probe-v1",
    "seed":SEED,
    "input_dims":int(x.shape[1]),
    "hidden_dims":32,
    "training_examples":len(train),
    "validation_examples":len(val),
    **best_stats,
    "frozen_at_runtime":True,
}
(DATA/"social_probe_v020a3.json").write_text(json.dumps(meta,indent=2),encoding="utf-8")
print(json.dumps(meta,indent=2))
