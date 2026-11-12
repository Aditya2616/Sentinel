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
    ap.add_argument("--base", default="microsoft/deberta-v3-xsmall")
    ap.add_argument("--out", default="models/sentinel")
    ap.add_argument("--epochs", type=int, default=6)
    ap.add_argument("--lr", type=float, default=5e-5)
    ap.add_argument("--batch-size", type=int, default=16)
    ap.add_argument("--max-length", type=int, default=256)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--threads", type=int, default=3)
    ap.add_argument("--train-set", default="train", help="processed training file: train, train_base, train_aug or train_ext")
    ap.add_argument("--select-dev", default="spml_dev", help="extra held-out set (e.g. spml_dev) averaged with validation PR-AUC for choosing the epoch")
    ap.add_argument("--patience", type=int, default=2, help="stop after this many epochs without improvement (0 = never)")
    ap.add_argument("--repeat-pool", action="append", default=None, help="POOL=K: repeat the rows of a training pool K times in total (default: hw_hn_train=4)")
    ap.add_argument("--device", default=None, help="cuda | cpu | auto (default: auto, or SENTINEL_DEVICE)")
    ap.add_argument("--limit", type=int, default=0, help="debug: use only N training rows")
    a = ap.parse_args(argv)

    import torch
    from transformers import (
        AutoModelForSequenceClassification,
        AutoTokenizer,
        get_linear_schedule_with_warmup,
    )

    from .classifier import pick_device

    device = pick_device(a.device)
    random.seed(a.seed)
    np.random.seed(a.seed)
    torch.manual_seed(a.seed)
    torch.set_num_threads(a.threads)

    if not (D.PROCESSED / "train.jsonl").exists():
        D.fetch()
        D.build()
    train, val = D.load(a.train_set), D.load("val")
    for spec in (a.repeat_pool if a.repeat_pool is not None else ["hw_hn_train=4"]):
        pool, k = spec.split("=")
        train = train + [r for r in train if r.get("pool") == pool] * (int(k) - 1)
    dev = D.load(f"test_{a.select_dev}") if a.select_dev else []
    if a.limit:
        random.Random(0).shuffle(train)
        train = train[: a.limit]
    print(f"device: {device}", flush=True)
    tok = AutoTokenizer.from_pretrained(a.base)
    model = AutoModelForSequenceClassification.from_pretrained(a.base, num_labels=2, dtype=torch.float32).to(device)

    def enc(rows):
        return [tok(r["text"], truncation=True, max_length=a.max_length)["input_ids"] for r in rows]

    Xtr, ytr = enc(train), [r["label"] for r in train]
    Xva, yva = enc(val), np.array([r["label"] for r in val])
    Xdev, ydev = enc(dev), np.array([r["label"] for r in dev])
    rng = random.Random(a.seed)
    steps = a.epochs * ((len(Xtr) + a.batch_size - 1) // a.batch_size)
    opt = torch.optim.AdamW(model.parameters(), lr=a.lr, weight_decay=0.01)
    sched = get_linear_schedule_with_warmup(opt, int(0.1 * steps), steps)

    def pad(seqs):
        return tok.pad({"input_ids": seqs}, return_tensors="pt").to(device)

    def predict(X):
        model.eval()
        order = sorted(range(len(X)), key=lambda k: len(X[k]))
        m = np.zeros(len(X))
        with torch.inference_mode():
            for i in range(0, len(order), 64):
                idx = order[i : i + 64]
                out = model(**pad([X[k] for k in idx])).logits.float()
                m[idx] = (out[:, 1] - out[:, 0]).cpu().numpy()
        model.train()
        return m

    def _step(idx, total=None):
        """Forward + backward for the rows in ``idx``; the loss is scaled when a batch is split."""
        batch = pad([Xtr[k] for k in idx])
        labels = torch.tensor([ytr[k] for k in idx], device=device)
        loss = torch.nn.functional.cross_entropy(model(**batch).logits, labels)
        (loss * (len(idx) / total) if total else loss).backward()
        return loss.item() * (len(idx) / total) if total else loss.item()

    log = {"base_model": a.base, "args": vars(a), "epochs": [], "n_train": len(Xtr), "n_val": len(Xva)}
    best_state, best_ap, best_val, stale = None, -1.0, -1.0, 0
    t0 = time.time()
    model.train()
    step = 0
    for ep in range(a.epochs):
        run = 0.0
        batches = _batches([len(x) for x in Xtr], a.batch_size, rng)
        for bi, idx in enumerate(batches):
            try:
                loss = _step(idx)
            except torch.cuda.OutOfMemoryError:  # the GPU may be shared: retry the batch in halves
                opt.zero_grad()
                torch.cuda.empty_cache()
                half = max(1, len(idx) // 2)
                loss = sum(_step(idx[i : i + half], len(idx)) for i in range(0, len(idx), half))
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            sched.step()
            opt.zero_grad()
            run += loss
            step += 1
            if bi % 50 == 0:
                print(f"epoch {ep + 1} step {bi}/{len(batches)} loss {run / (bi + 1):.4f} elapsed {time.time() - t0:.0f}s", flush=True)
        m = predict(Xva)
        ap_val, auc = average_precision(yva, m), auc_roc(yva, m)
        acc = float(((m > 0) == yva.astype(bool)).mean())
        dev_ap = average_precision(ydev, predict(Xdev)) if len(Xdev) else None
        sel = ap_val if dev_ap is None else (ap_val + dev_ap) / 2
        log["epochs"].append({"epoch": ep + 1, "train_loss": run / len(batches), "val_pr_auc": ap_val, "val_roc_auc": auc, "val_acc@0": acc, "dev_pr_auc": dev_ap, "select_score": sel, "elapsed_s": time.time() - t0})
        print(f"== epoch {ep + 1}: val PR-AUC {ap_val:.4f} ROC-AUC {auc:.4f} acc {acc:.4f} dev PR-AUC {dev_ap if dev_ap is None else round(dev_ap, 4)}", flush=True)
        if sel > best_ap:
            best_ap, stale = sel, 0
            best_state = {k: v.detach().clone() for k, v in model.state_dict().items()}
            best_val = ap_val
        else:
            stale += 1
            if a.patience and stale >= a.patience:
                print(f"early stop after epoch {ep + 1}", flush=True)
                break
    model.load_state_dict(best_state)
    m = predict(Xva)
    T = fit_temperature(m, yva)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(out)
    tok.save_pretrained(out)
    log["train_seconds"] = time.time() - t0
    log["threads"] = a.threads
    log["device"] = device
    log["gpu"] = torch.cuda.get_device_name(0) if device == "cuda" else None
    log["torch"] = torch.__version__
    (out / "calibration.json").write_text(json.dumps({"temperature": T, "base_model": a.base, "max_length": a.max_length, "val_pr_auc": best_val, "select_score": best_ap, "select_dev": a.select_dev or None, "train_set": a.train_set}, indent=2))
    (out / "training_log.json").write_text(json.dumps(log, indent=2))
    print(f"saved {out}  temperature={T:.3f}  train time {log['train_seconds']:.0f}s")


if __name__ == "__main__":
    main()
