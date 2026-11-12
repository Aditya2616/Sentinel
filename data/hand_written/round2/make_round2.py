"""Generate the round-two hand-written sets as JSONL and (once) freeze the v2 test sets.

    python data/hand_written/round2/make_round2.py            # writes the JSONL files
    python data/hand_written/round2/make_round2.py --freeze   # also records the SHA-256 of the v2 test files

The v2 test files are frozen: tests/test_frozen_v2.py fails if they change after being frozen.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent
sys.path.insert(0, str(HERE))

from test_v2 import ATTACKS_V2, HARD_BENIGN_V2  # noqa: E402


def digest(path: Path) -> str:
    """SHA-256 of the file with line endings normalised, so a Windows checkout hashes the same as a Linux one."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def write(name: str, texts: list[str], label: int, category: str) -> Path:
    p = OUT / name
    with p.open("w", encoding="utf-8", newline="\n") as f:
        for t in texts:
            f.write(json.dumps({"text": t, "label": label, "category": category}, ensure_ascii=False) + "\n")
    return p


def main() -> None:
    files = [
        write("hard_benign_v2_test.jsonl", HARD_BENIGN_V2, 0, "hard_benign_v2"),
        write("attacks_v2_test.jsonl", ATTACKS_V2, 1, "plain_attack_v2"),
    ]
    try:  # the validation and training hard-negative sets are written separately, after the v2 test sets were frozen
        from train_val import HARD_NEG_TRAIN, HARD_NEG_VAL

        files.append(write("hard_neg_val.jsonl", HARD_NEG_VAL, 0, "hard_neg_val"))
        files.append(write("hard_neg_train.jsonl", HARD_NEG_TRAIN, 0, "hard_neg_train"))
    except ImportError:
        pass
    for f in files:
        print(f.name, sum(1 for _ in f.open(encoding="utf-8")))
    if "--freeze" in sys.argv:
        sums = {f.name: digest(f) for f in files if "_v2_test" in f.name}
        (OUT / "FROZEN_V2.json").write_text(json.dumps(sums, indent=2) + "\n", encoding="utf-8")
        print("frozen", sums)


if __name__ == "__main__":
    main()
