"""Fine-tune a small encoder on the processed training split (CPU).

    sentinel train                 # builds the data if needed, trains, calibrates, saves to models/
"""

from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path

import numpy as np

from . import data as D
from .metrics import auc_roc, average_precision


def _batches(lengths: list[int], bs: int, rng: random.Random) -> list[list[int]]:
    idx = list(range(len(lengths)))
    rng.shuffle(idx)
    mega = bs * 50
    out: list[list[int]] = []
    for i in range(0, len(idx), mega):
        chunk = sorted(idx[i : i + mega], key=lambda k: lengths[k])
        out += [chunk[j : j + bs] for j in range(0, len(chunk), bs)]
    rng.shuffle(out)
    return out


def fit_temperature(logits: np.ndarray, y: np.ndarray) -> float:
    """Single-parameter temperature scaling on the validation logit margin (minimise NLL)."""
    import torch

    z = torch.tensor(logits, dtype=torch.float64)
    t = torch.tensor(y, dtype=torch.float64)
    logT = torch.zeros(1, dtype=torch.float64, requires_grad=True)
    opt = torch.optim.LBFGS([logT], lr=0.1, max_iter=100)

    def closure():
        opt.zero_grad()
        loss = torch.nn.functional.binary_cross_entropy_with_logits(z / logT.exp(), t)
        loss.backward()
        return loss

    opt.step(closure)
    return float(logT.exp().item())


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Fine-tune the Sentinel classifier")
    ap.add_argument("--base", default="sentence-transformers/all-MiniLM-L6-v2")
    ap.add_argument("--out", default="models/sentinel-minilm")
    ap.add_argument("--epochs", type=int, default=2)
    ap.add_argument("--lr", type=float, default=5e-5)
    ap.add_argument("--batch-size", type=int, default=16)
    ap.add_argument("--max-length", type=int, default=128)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--threads", type=int, default=3)
    ap.add_argument("--limit", type=int, default=0, help="debug: use only N training rows")
    a = ap.parse_args(argv)

    import torch
    from transformers import (
        AutoModelForSequenceClassification,
        AutoTokenizer,
        get_linear_schedule_with_warmup,
    )

    random.seed(a.seed)
    np.random.seed(a.seed)
    torch.manual_seed(a.seed)
    torch.set_num_threads(a.threads)

    if not (D.PROCESSED / "train.jsonl").exists():
        D.fetch()
        D.build()
    train, val = D.load("train"), D.load("val")
    if a.limit:
        random.Random(0).shuffle(train)
        train = train[: a.limit]
    tok = AutoTokenizer.from_pretrained(a.base)
    model = AutoModelForSequenceClassification.from_pretrained(a.base, num_labels=2)

    def enc(rows):
        return [tok(r["text"], truncation=True, max_length=a.max_length)["input_ids"] for r in rows]

    Xtr, ytr = enc(train), [r["label"] for r in train]
    Xva, yva = enc(val), np.array([r["label"] for r in val])
    rng = random.Random(a.seed)
    steps = a.epochs * ((len(Xtr) + a.batch_size - 1) // a.batch_size)
    opt = torch.optim.AdamW(model.parameters(), lr=a.lr, weight_decay=0.01)
    sched = get_linear_schedule_with_warmup(opt, int(0.1 * steps), steps)

    def pad(seqs):
        return tok.pad({"input_ids": seqs}, return_tensors="pt")

    def predict(X):
        model.eval()
        order = sorted(range(len(X)), key=lambda k: len(X[k]))
        m = np.zeros(len(X))
        with torch.inference_mode():
            for i in range(0, len(order), 64):
                idx = order[i : i + 64]
                out = model(**pad([X[k] for k in idx])).logits.float()
                m[idx] = (out[:, 1] - out[:, 0]).numpy()
        model.train()
        return m

    log = {"base_model": a.base, "args": vars(a), "epochs": [], "n_train": len(Xtr), "n_val": len(Xva)}
    best_state, best_ap = None, -1.0
    t0 = time.time()
    model.train()
    step = 0
    for ep in range(a.epochs):
        run = 0.0
        batches = _batches([len(x) for x in Xtr], a.batch_size, rng)
        for bi, idx in enumerate(batches):
            batch = pad([Xtr[k] for k in idx])
            labels = torch.tensor([ytr[k] for k in idx])
            loss = torch.nn.functional.cross_entropy(model(**batch).logits, labels)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            sched.step()
            opt.zero_grad()
            run += loss.item()
            step += 1
            if bi % 50 == 0:
                print(f"epoch {ep + 1} step {bi}/{len(batches)} loss {run / (bi + 1):.4f} elapsed {time.time() - t0:.0f}s", flush=True)
        m = predict(Xva)
        ap_val, auc = average_precision(yva, m), auc_roc(yva, m)
        acc = float(((m > 0) == yva.astype(bool)).mean())
        log["epochs"].append({"epoch": ep + 1, "train_loss": run / len(batches), "val_pr_auc": ap_val, "val_roc_auc": auc, "val_acc@0": acc, "elapsed_s": time.time() - t0})
        print(f"== epoch {ep + 1}: val PR-AUC {ap_val:.4f} ROC-AUC {auc:.4f} acc {acc:.4f}", flush=True)
        if ap_val > best_ap:
            best_ap = ap_val
            best_state = {k: v.detach().clone() for k, v in model.state_dict().items()}
    model.load_state_dict(best_state)
    m = predict(Xva)
    T = fit_temperature(m, yva)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(out)
    tok.save_pretrained(out)
    log["train_seconds"] = time.time() - t0
    log["threads"] = a.threads
    log["torch"] = torch.__version__
    (out / "calibration.json").write_text(json.dumps({"temperature": T, "base_model": a.base, "max_length": a.max_length}, indent=2))
    (out / "training_log.json").write_text(json.dumps(log, indent=2))
    print(f"saved {out}  temperature={T:.3f}  train time {log['train_seconds']:.0f}s")


if __name__ == "__main__":
    main()
