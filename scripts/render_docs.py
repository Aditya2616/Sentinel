"""Fill the generated result blocks in README.md and MODEL_CARD.md from docs/data/eval.json.

    python scripts/render_docs.py

Blocks look like ``<!-- BEGIN:name -->`` ... ``<!-- END:name -->``; everything between the markers is replaced.
No number in those blocks is typed by hand.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
E = json.loads((ROOT / "docs" / "data" / "eval.json").read_text(encoding="utf-8"))
R = E["results"]
LABEL = {
    "indist": "In-distribution test (neuralchemy + jackhhao)",
    "deepset": "deepset/prompt-injections (OOD, EN+DE)",
    "spml": "SPML (OOD)",
    "hard_benign": "Hard-benign (talks about injection)",
    "obfuscated": "Obfuscated attacks and benign",
    "attacks": "Plain attacks (hand-written)",
    "dolly_benign": "Everyday benign (Dolly-15k held out)",
    "indirect": "Indirect injection in documents (SYNTHETIC)",
}
SYS = {"rules_only": "Rules only", "tfidf": "TF-IDF + LR", "classifier": "Classifier only", "sentinel": "Sentinel (rules + classifier)"}


def pc(x, d=1):
    return "n/a" if x is None else f"{x * 100:.{d}f}%"


def ci(pair):
    return "" if not pair else f" [{pair[0] * 100:.1f}, {pair[1] * 100:.1f}]"


def num(x, d=3):
    return "n/a" if x is None else f"{x:.{d}f}"


def headline() -> str:
    s = R["sentinel"]
    rows = [
        ("False-positive rate on hard-benign text (blocked / benign prompts that talk about injection)", s["hard_benign"], "fpr", "fpr_ci", "{fp} of {n_neg}"),
        ("Recall on deepset/prompt-injections (out of distribution)", s["deepset"], "recall", "recall_ci", "{tp} of {n_pos}"),
        ("Recall on SPML (out of distribution)", s["spml"], "recall", "recall_ci", "{tp} of {n_pos}"),
        ("False-positive rate on everyday benign (Dolly-15k held out)", s["dolly_benign"], "fpr", "fpr_ci", "{fp} of {n_neg}"),
    ]
    out = ["| Headline (Sentinel, block decision) | Value | 95% Wilson interval | Counts |", "|---|---|---|---|"]
    for name, e, k, kc, cnt in rows:
        c = e["confusion"]
        counts = cnt.format(**c, n_pos=e["n_pos"], n_neg=e["n_neg"])
        iv = e.get(kc)
        out.append(f"| {name} | {pc(e[k])} | {('%.1f%% to %.1f%%' % (iv[0] * 100, iv[1] * 100)) if iv else 'n/a'} | {counts} |")
    i = s["indist"]
    out.append(f"| In-distribution F1 (secondary; the training data is partly synthetic) | {num(i['f1'])} | | n={i['n']} |")
    return "\n".join(out)


def per_set() -> str:
    out = ["| Test set | n (attacks / benign) | System | Recall | FPR | F1 | ROC-AUC |", "|---|---|---|---|---|---|---|"]
    for n, lab in LABEL.items():
        for sname, sl in SYS.items():
            e = R[sname][n]
            tag = f"{e['n']} ({e['n_pos']} / {e['n_neg']})" if sname == "rules_only" else ""
            out.append(
                f"| {lab if sname == 'rules_only' else ''} | {tag} | {sl} | "
                f"{pc(e['recall']) if e['n_pos'] else 'n/a'}{ci(e.get('recall_ci')) if e['n_pos'] else ''} | "
                f"{pc(e['fpr']) if e['n_neg'] else 'n/a'}{ci(e.get('fpr_ci')) if e['n_neg'] else ''} | "
                f"{num(e['f1']) if e['n_pos'] and e['n_neg'] else 'n/a'} | {num(e.get('roc_auc'))} |"
            )
    return "\n".join(out)


def language() -> str:
    out = ["| deepset subset | n | attacks | Recall (Sentinel) | FPR (Sentinel) | Recall (classifier only) |", "|---|---|---|---|---|---|"]
    for lg, e in E["deepset_by_language"].items():
        out.append(f"| {lg.upper()} | {e['n']} | {e['n_pos']} | {pc(e['recall'])} | {pc(e['fpr'])} | {pc(e['classifier_only']['recall'])} |")
    return "\n".join(out)


def latency() -> str:
    L = E["latency"]
    rows = [("Rules only", "rules_only"), ("Classifier, one prompt at a time", "classifier_single"), ("Full Sentinel, one prompt", "sentinel_full"), ("TF-IDF + LR", "tfidf")]
    out = ["| Path | p50 (ms) | p95 (ms) |", "|---|---|---|"]
    for lab, k in rows:
        out.append(f"| {lab} | {L[k]['p50_ms']:.1f} | {L[k]['p95_ms']:.1f} |")
    out.append(f"\nClassifier in batches of 64: {L['classifier_batch64_ms_per_prompt']:.1f} ms per prompt. {L['note']} Threads: {L['threads']}.")
    return "\n".join(out)


def thresholds() -> str:
    t = E["meta"]["thresholds"]
    sel = E["meta"]["threshold_selection"]
    return (
        f"Chosen on the validation split only (n={sel['val_n']}): block at calibrated score >= {t['t_block']:.3f} (1% validation FPR), "
        f"flag at >= {t['t_flag']:.3f} (3%), agreement threshold {t['t_agree']:.3f} (10%). Policy: {json.dumps(t)}"
    )


def training() -> str:
    tl = E["meta"]["training_log"]
    ep = tl["epochs"]
    sizes = E["meta"]["build_report"]["sizes"]
    lines = [
        f"- Base model: `{tl['base_model']}`; {tl['n_train']} training rows, {tl['n_val']} validation rows; "
        f"{tl['args']['epochs']} epochs, lr {tl['args']['lr']}, batch {tl['args']['batch_size']}, max length {tl['args']['max_length']}, seed {tl['args']['seed']}.",
        f"- CPU training time: {tl['train_seconds'] / 60:.0f} minutes with {tl['threads']} threads (torch {tl['torch']}), on a machine that was busy with other jobs.",
    ]
    for e in ep:
        lines.append(f"- Epoch {e['epoch']}: train loss {e['train_loss']:.3f}, validation PR-AUC {e['val_pr_auc']:.4f}, ROC-AUC {e['val_roc_auc']:.4f}.")
    lines.append("- Split sizes after de-duplication: " + ", ".join(f"{k} {v['n']} ({v['malicious']} attacks)" for k, v in sizes.items()) + ".")
    return "\n".join(lines)


def shortcuts() -> str:
    s = E["shortcuts"]
    a = ", ".join(f"{k} {num(v, 2)}" for k, v in s["length_only_roc_auc"].items())
    b = ", ".join(f"{k} {num(v, 2)}" for k, v in s["label_shuffled_tfidf_roc_auc"].items())
    return f"- Length-only logistic regression, ROC-AUC: {a} (0.50 is chance).\n- TF-IDF trained on shuffled labels, ROC-AUC: {b} (should be near 0.50)."


def errors() -> str:
    e = E["errors"]
    return f"Sentinel blocked {len(e['false_positives'])} benign test prompts and let {len(e['false_negatives'])} attacks through (first 60 of each are stored in `docs/data/eval.json` under `errors`)."


BLOCKS = {"headline": headline, "per_set": per_set, "language": language, "latency": latency, "thresholds": thresholds, "training": training, "shortcuts": shortcuts, "errors": errors}


def fill(path: Path) -> None:
    if not path.exists():
        return
    s = path.read_text(encoding="utf-8")
    for name, fn in BLOCKS.items():
        pat = re.compile(rf"(<!-- BEGIN:{name} -->)(.*?)(<!-- END:{name} -->)", re.S)
        s = pat.sub(lambda m: f"{m.group(1)}\n{fn()}\n{m.group(3)}", s)
    path.write_text(s, encoding="utf-8", newline="\n")
    print("updated", path.name)


if __name__ == "__main__":
    fill(ROOT / "README.md")
    fill(ROOT / "MODEL_CARD.md")
