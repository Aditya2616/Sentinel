"""Fill sets that did not exist in round one into docs/data/baseline_round1.json, using the round-one model and its published thresholds.

    python scripts/score_snapshot.py models/r1     # the round-one model directory (retrain it with the round-one recipe in the README)

Only sets introduced in round two are touched; the numbers already in the file are what round one published.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

from sentinel import data as D
from sentinel.classifier import TransformerClassifier
from sentinel.decision import Thresholds
from sentinel.metrics import confusion, prf
from sentinel.screen import Sentinel

NEW_SETS = ["hard_benign_dedup", "hard_benign_v2", "attacks_v2"]


def main(model_dir: str) -> None:
    p = Path("docs/data/baseline_round1.json")
    rec = json.loads(p.read_text(encoding="utf-8"))
    sent = Sentinel(TransformerClassifier(Path(model_dir)), Thresholds(**{k: v for k, v in rec["thresholds"].items() if k != "preset"}))
    for n in NEW_SETS:
        rows = D.load(f"test_{n}")
        y = np.array([r["label"] for r in rows])
        dec = sent.screen_batch([r["text"] for r in rows])
        blk = np.array([d.action == "block" for d in dec])
        alr = np.array([d.action != "allow" for d in dec])
        c, ca = confusion(y, blk), confusion(y, alr)
        rec["results"]["sentinel"][n] = {"n": len(y), "n_pos": int(y.sum()), "n_neg": int((1 - y).sum()), "confusion": c, **prf(c), "alert": {"confusion": ca, **prf(ca)}}
    p.write_text(json.dumps(rec, separators=(",", ":"), default=float), encoding="utf-8")
    print({n: rec["results"]["sentinel"][n]["confusion"] for n in NEW_SETS})


if __name__ == "__main__":
    main(sys.argv[1])
