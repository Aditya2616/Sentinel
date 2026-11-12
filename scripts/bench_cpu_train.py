"""Time a few real training steps on the CPU and extrapolate the cost of `sentinel train` there.

    python scripts/bench_cpu_train.py [base_model] [threads] [steps] [epochs] > docs/data/cpu_train_bench.json

Uses the same batch size, max length and length-bucketed batches as `sentinel train`. The extrapolation is an
estimate (it assumes the later steps cost the same as the measured ones) and depends on how busy the machine is.
"""

from __future__ import annotations

import json
import random
import sys
import time

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from sentinel import data as D
from sentinel.sysinfo import load_note
from sentinel.train import _batches

base = sys.argv[1] if len(sys.argv) > 1 else "sentence-transformers/all-MiniLM-L6-v2"
threads = int(sys.argv[2]) if len(sys.argv) > 2 else 3
steps = int(sys.argv[3]) if len(sys.argv) > 3 else 12
epochs = int(sys.argv[4]) if len(sys.argv) > 4 else 3
load = load_note()
torch.set_num_threads(threads)
tok = AutoTokenizer.from_pretrained(base)
model = AutoModelForSequenceClassification.from_pretrained(base, num_labels=2, dtype=torch.float32).train()
train = D.load("train")
X = [tok(r["text"], truncation=True, max_length=256)["input_ids"] for r in train]
y = [r["label"] for r in train]
batches = _batches([len(x) for x in X], 16, random.Random(42))
opt = torch.optim.AdamW(model.parameters(), lr=5e-5)
times = []
for idx in batches[: steps + 1]:
    t0 = time.perf_counter()
    b = tok.pad({"input_ids": [X[k] for k in idx]}, return_tensors="pt")
    loss = torch.nn.functional.cross_entropy(model(**b).logits, torch.tensor([y[k] for k in idx]))
    loss.backward()
    opt.step()
    opt.zero_grad()
    times.append(time.perf_counter() - t0)
per = sum(times[1:]) / len(times[1:])  # the first step includes warm-up
total_steps = epochs * len(batches)
print(json.dumps({
    "base": base, "epochs": epochs, "threads": threads, "steps_timed": len(times) - 1, "seconds_per_step": round(per, 2),
    "steps_per_run": total_steps, "estimated_minutes_for_full_run": round(per * total_steps / 60, 1),
    "load": load, "cpu_count": __import__("os").cpu_count(), "device": "cpu (float32)",
    "note": "estimate: measured steps extrapolated to the given number of epochs, excludes validation passes",
}))
