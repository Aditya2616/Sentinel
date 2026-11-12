"""Choose between trained classifier variants using validation and OOD-dev only (never deepset, the OOD-test half or any test set).

    python scripts/ablation.py label=models/dir [label=models/dir ...] > docs/data/ablation.json

Rule, fixed before the round-two models were trained: each model gets the "balanced" block threshold (the lowest threshold with
validation hard-benign FPR at or below 2% and validation everyday-benign FPR at or below 0.5%); among models, the one with the
best OOD-dev recall at that threshold is the default. The output also lists OOD-dev recall at the thresholds giving 1%, 2% and 5%
hard-benign validation FPR.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

from sentinel import data as D
from sentinel.classifier import TransformerClassifier
from sentinel.evaluate import PRESET_CAPS, lowest_threshold, val_masks
from sentinel.metrics import average_precision, threshold_at_fpr


def main(specs: list[str]) -> None:
    val, dev = D.load("val"), D.load("test_spml_dev")
    vy, dy = np.array([r["label"] for r in val]), np.array([r["label"] for r in dev])
    hb, dolly = val_masks(val)
    out = []
    for spec in specs:
        label, path = spec.split("=", 1)
        clf = TransformerClassifier(Path(path))
        vs, ds = clf.score([r["text"] for r in val]), clf.score([r["text"] for r in dev])
        log = json.loads((Path(path) / "training_log.json").read_text())
        thr = lowest_threshold(vs, hb, dolly, PRESET_CAPS["balanced"]["block"])
        at = {}
        for lv in (0.01, 0.02, 0.05):
            t = float(threshold_at_fpr(np.zeros(int(hb.sum())), vs[hb], lv))
            at[str(lv)] = float(((ds >= t) & (dy == 1)).sum() / dy.sum())
        out.append(
            {
                "variant": label,
                "model": log["base_model"],
                "train_rows": log["n_train"],
                "epochs_run": len(log["epochs"]),
                "val_pr_auc": average_precision(vy, vs),
                "dev_pr_auc": average_precision(dy, ds),
                "balanced_block_threshold": thr,
                "dev_recall_at_balanced": float(((ds >= thr) & (dy == 1)).sum() / dy.sum()),
                "dev_fpr_at_balanced": float(((ds >= thr) & (dy == 0)).sum() / (dy == 0).sum()),
                "val_hard_benign_n": int(hb.sum()),
                "val_hard_benign_fpr_at_balanced": float((vs[hb] >= thr).mean()),
                "val_everyday_fpr_at_balanced": float((vs[dolly] >= thr).mean()),
                "dev_recall_at_hard_benign_val_fpr": at,
            }
        )
    best = max(range(len(out)), key=lambda i: out[i]["dev_recall_at_balanced"])
    for i, r in enumerate(out):
        r["selected"] = i == best
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main(sys.argv[1:])
