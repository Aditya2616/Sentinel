"""Compare trained classifier variants using validation and OOD-dev only (never deepset or the OOD-test half).

    python scripts/ablation.py label=models/dir [label=models/dir ...] > docs/data/ablation.json

For each model: validation PR-AUC, OOD-dev (the SPML half used for selection) PR-AUC, and, at the threshold that gives
1% false-positive rate on the validation split, the OOD-dev recall and false-positive rate and the false-positive rate
on the validation split's hard-benign examples (the examples that talk about injection).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

from sentinel import data as D
from sentinel.classifier import TransformerClassifier
from sentinel.metrics import average_precision, threshold_at_fpr


def main(specs: list[str]) -> None:
    val, dev = D.load("val"), D.load("test_spml_dev")
    vy, dy = np.array([r["label"] for r in val]), np.array([r["label"] for r in dev])
    hb = np.array([r.get("pool") == "hw_hard_benign_val" for r in val])
    out = []
    for spec in specs:
        label, path = spec.split("=", 1)
        clf = TransformerClassifier(Path(path))
        vs, ds = clf.score([r["text"] for r in val]), clf.score([r["text"] for r in dev])
        thr = threshold_at_fpr(vy, vs, 0.01)
        log = json.loads((Path(path) / "training_log.json").read_text())
        out.append(
            {
                "variant": label,
                "train_rows": log["n_train"],
                "epochs_run": len(log["epochs"]),
                "val_pr_auc": average_precision(vy, vs),
                "dev_pr_auc": average_precision(dy, ds),
                "threshold_at_1pct_val_fpr": thr,
                "dev_recall_at_that_threshold": float(((ds >= thr) & (dy == 1)).sum() / dy.sum()),
                "dev_fpr_at_that_threshold": float(((ds >= thr) & (dy == 0)).sum() / (dy == 0).sum()),
                "val_hard_benign_n": int(hb.sum()),
                "val_hard_benign_fpr_at_that_threshold": float((vs[hb] >= thr).mean()),
            }
        )
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main(sys.argv[1:])
