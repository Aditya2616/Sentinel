"""The v2 test sets were written and frozen before any model trained on the round-two data was run."""

import hashlib
import json
from pathlib import Path

HAND = Path(__file__).resolve().parents[1] / "data" / "hand_written"


def test_v2_test_sets_are_unchanged():
    frozen = json.loads((HAND / "FROZEN_V2.json").read_text(encoding="utf-8"))
    assert set(frozen) == {"hard_benign_v2_test.jsonl", "attacks_v2_test.jsonl"}
    for name, digest in frozen.items():
        data = (HAND / name).read_bytes().replace(b"\r\n", b"\n")
        assert hashlib.sha256(data).hexdigest() == digest, f"{name} changed after it was frozen"


def test_round_two_sets_do_not_overlap():
    import re

    def load(n):
        return [json.loads(line)["text"] for line in (HAND / f"{n}.jsonl").read_text(encoding="utf-8").split("\n") if line.strip()]

    names = ["hard_neg_val", "hard_neg_train", "hard_benign_v2_test", "hard_benign_test"]
    sets = {n: load(n) for n in names}
    assert len(sets["hard_neg_val"]) >= 120 and len(sets["hard_benign_v2_test"]) >= 80 and len(load("attacks_v2_test")) >= 30
    tok = lambda t: set(re.findall(r"\w+", t.lower()))  # noqa: E731
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            ta = [tok(t) for t in sets[a]]
            for t in sets[b]:
                w = tok(t)
                assert all(len(w & x) / max(1, len(w | x)) < 0.8 for x in ta), f"near-duplicate between {a} and {b}: {t[:60]}"
