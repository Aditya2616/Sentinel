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
LBL = E["meta"].get("system_labels", {})
SYS = {k: LBL[k] for k in ("rules_only", "tfidf", "classifier_alt", "classifier", "sentinel") if k in R and k in LBL}


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
        out.append(f"| {name} | {pc(e[k])} | {f'{iv[0] * 100:.1f}% to {iv[1] * 100:.1f}%' if iv else 'n/a'} | {counts} |")
    d = s["deepset"]
    out.append(f"| Recall on deepset counting a flag as a catch (flagged prompts still reach the model) | {pc(d['alert']['recall'])} | | n={d['n_pos']} attacks |")
    i = s["indist"]
    out.append(f"| In-distribution F1 (secondary; the training data is partly synthetic) | {num(i['f1'])} | | n={i['n']} |")
    return "\n".join(out)


def per_set() -> str:
    out = ["| Test set | n (attacks / benign) | System | Recall (block) | Recall (flag or block) | FPR (block) | F1 | ROC-AUC |", "|---|---|---|---|---|---|---|---|"]
    for n, lab in LABEL.items():
        for sname, sl in SYS.items():
            e = R[sname][n]
            tag = f"{e['n']} ({e['n_pos']} / {e['n_neg']})" if sname == "rules_only" else ""
            out.append(
                f"| {lab if sname == 'rules_only' else ''} | {tag} | {sl} | "
                f"{pc(e['recall']) if e['n_pos'] else 'n/a'}{ci(e.get('recall_ci')) if e['n_pos'] else ''} | "
                f"{pc(e['alert']['recall']) if 'alert' in e and e['n_pos'] else '-'} | "
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
    out.append(f"\nCPU, classifier in batches of 64: {L['classifier_batch64_ms_per_prompt']:.1f} ms per prompt. {L['note']}")
    g = L.get("gpu")
    if g:
        out.append(
            f"\nGPU ({g['device']}, float32) for comparison: classifier {g['classifier_single']['p50_ms']:.1f} ms p50 / {g['classifier_single']['p95_ms']:.1f} ms p95 per prompt, "
            f"full Sentinel {g['sentinel_full']['p50_ms']:.1f} / {g['sentinel_full']['p95_ms']:.1f} ms, batches of 64: {g['classifier_batch64_ms_per_prompt']:.1f} ms per prompt."
        )
    return "\n".join(out)


def thresholds() -> str:
    t = E["meta"]["thresholds"]
    sel = E["meta"]["threshold_selection"]
    return (
        f"Chosen on the validation split only (n={sel['val_n']}): block at calibrated score >= {t['t_block']:.3f} (1% validation FPR), "
        f"flag at >= {t['t_flag']:.3f} (3%), agreement threshold {t['t_agree']:.3f} (10%). Policy: {json.dumps(t)}"
    )


def _train_lines(tl: dict, title: str) -> list[str]:
    where = f"{tl.get('gpu') or 'CPU'} ({tl.get('device', 'cpu')}, float32)"
    lines = [
        f"- **{title}: `{tl['base_model']}`** on {where}: {tl['n_train']} training rows, {tl['n_val']} validation rows; "
        f"{tl['args']['epochs']} epochs, lr {tl['args']['lr']}, batch {tl['args']['batch_size']}, max length {tl['args']['max_length']}, seed {tl['args']['seed']}; "
        f"{tl['train_seconds']:.0f} s of training.",
    ]
    for e in tl["epochs"]:
        lines.append(f"  - epoch {e['epoch']}: train loss {e['train_loss']:.3f}, validation PR-AUC {e['val_pr_auc']:.4f}, ROC-AUC {e['val_roc_auc']:.4f}")
    return lines


def training() -> str:
    m = E["meta"]
    lines = _train_lines(m["training_log"], "Shipped default")
    if m.get("alt_training_log"):
        lines += _train_lines(m["alt_training_log"], "Compared")
        lines.append(
            "- Selection rule, fixed before I looked at any test set: among variants trained on the same data, take the highest OOD-dev recall at the validation 1%-FPR threshold, "
            "provided the validation hard-benign false-positive rate does not rise and validation PR-AUC drops by no more than 0.005. See the ablation table."
        )
    for bench in sorted((ROOT / "docs" / "data").glob("cpu_train_bench*.json")):
        b = json.loads(bench.read_text(encoding="utf-8"))
        lines.append(
            f"- CPU training time, **estimate** for `{b['base']}`: `scripts/bench_cpu_train.py` timed {b['steps_timed']} real steps at {b['seconds_per_step']} s/step with {b['threads']} threads "
            f"({b['cpu_count']} logical cores; {b['load']}), which extrapolates to about {b['estimated_minutes_for_full_run']} minutes for {b['epochs']} epochs ({b['steps_per_run']} steps), "
            "excluding validation passes. It is an extrapolation, and a busier machine is slower."
        )
    sizes = m["build_report"]["sizes"]
    lines.append("- Split sizes after de-duplication: " + ", ".join(f"{k} {v['n']} ({v['malicious']} attacks)" for k, v in sizes.items()) + ".")
    return "\n".join(lines)


def shortcuts() -> str:
    s = E["shortcuts"]
    a = ", ".join(f"{k} {num(v, 2)}" for k, v in s["length_only_roc_auc"].items())
    b = ", ".join(f"{k} {num(v, 2)}" for k, v in s["label_shuffled_tfidf_roc_auc"].items())
    return f"- Length-only logistic regression, ROC-AUC: {a} (0.50 is chance).\n- TF-IDF trained on shuffled labels, ROC-AUC: {b} (should be near 0.50)."


def operating() -> str:
    """Recall when the score threshold is set to a fixed false-positive rate on each set's own benign side."""
    rows = [("deepset", "deepset (OOD)"), ("spml", "SPML OOD-test"), ("indist", "In-distribution"), ("obfuscated", "Obfuscated"), ("indirect", "Indirect (synthetic)")]
    keys = [k for k in ("classifier", "classifier_alt", "tfidf") if k in R]
    out = ["| Test set | " + " | ".join(f"{LBL[k]} @1% / @5% FPR" for k in keys) + " |", "|---|" + "---|" * len(keys)]
    for n, lab in rows:
        cells = []
        for k in keys:
            r = R[k][n].get("recall_at_fpr")
            cells.append("n/a" if not r else f"{pc(r['0.01'])} / {pc(r['0.05'])}")
        out.append(f"| {lab} | " + " | ".join(cells) + " |")
    return "\n".join(out)


def before_after() -> str:
    p = ROOT / "docs" / "data" / "baseline_v1.json"
    if not p.exists():
        return "No baseline recorded."
    B = json.loads(p.read_text(encoding="utf-8"))["results"]
    rows = [("deepset", "deepset (OOD, untouched)"), ("spml", "SPML OOD-test"), ("spml_dev", "SPML OOD-dev (selection only)"), ("indist", "In-distribution"), ("obfuscated", "Obfuscated"), ("attacks", "Plain attacks"), ("indirect", "Indirect (SYNTHETIC)")]
    out = ["| Set | Recall block, before | after | Recall flag-or-block, before | after | Classifier recall @1% FPR, before | after |", "|---|---|---|---|---|---|---|"]
    for n, lab in rows:
        b, a = B["sentinel"][n], R["sentinel"][n]
        bq, aq = B["classifier"][n].get("recall_at_fpr"), R["classifier"][n].get("recall_at_fpr")
        out.append(
            f"| {lab} | {pc(b['recall'])} | {pc(a['recall'])} | {pc(b['alert']['recall'])} | {pc(a['alert']['recall'])} | "
            f"{pc(bq['0.01']) if bq else 'n/a'} | {pc(aq['0.01']) if aq else 'n/a'} |"
        )
    out += ["", "| Benign side | False-positive rate (block), before | after | n |", "|---|---|---|---|"]
    for n, lab in [("hard_benign", "Hard-benign (talks about injection)"), ("dolly_benign", "Everyday (Dolly-15k held out)"), ("spml", "SPML OOD-test benign"), ("deepset", "deepset benign")]:
        b, a = B["sentinel"][n], R["sentinel"][n]
        out.append(f"| {lab} | {pc(b['fpr'])} [{b['confusion']['fp']} of {b['n_neg']}] | {pc(a['fpr'])} [{a['confusion']['fp']} of {a['n_neg']}] | {a['n_neg']} |")
    return "\n".join(out)


def ablation() -> str:
    p = ROOT / "docs" / "data" / "ablation.json"
    if not p.exists():
        return "No ablation recorded."
    rows = json.loads(p.read_text(encoding="utf-8"))
    out = ["| Variant (selection uses validation + OOD-dev only) | Train rows | Epochs run | Val PR-AUC | OOD-dev PR-AUC | OOD-dev recall @ val 1% FPR | OOD-dev FPR | Val hard-benign FPR |", "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        out.append(
            f"| {r['variant']} | {r['train_rows']} | {r['epochs_run']} | {r['val_pr_auc']:.4f} | {r['dev_pr_auc']:.4f} | {pc(r['dev_recall_at_that_threshold'])} | "
            f"{pc(r['dev_fpr_at_that_threshold'])} | {pc(r['val_hard_benign_fpr_at_that_threshold'])} (n={r['val_hard_benign_n']}) |"
        )
    return "\n".join(out)


def errors() -> str:
    e = E["errors"]
    return f"Sentinel blocked {len(e['false_positives'])} benign test prompts and let {len(e['false_negatives'])} attacks through (first 60 of each are stored in `docs/data/eval.json` under `errors`)."


BLOCKS = {"headline": headline, "per_set": per_set, "language": language, "latency": latency, "thresholds": thresholds, "training": training, "shortcuts": shortcuts, "errors": errors, "operating": operating, "before_after": before_after, "ablation": ablation}


def fill(path: Path) -> None:
    if not path.exists():
        return
    s = path.read_text(encoding="utf-8")
    for name, fn in BLOCKS.items():
        pat = re.compile(rf"(<!-- BEGIN:{name} -->)(.*?)(<!-- END:{name} -->)", re.S)
        body = fn()
        s = pat.sub(lambda m, body=body: f"{m.group(1)}\n{body}\n{m.group(3)}", s)
    path.write_text(s, encoding="utf-8", newline="\n")
    print("updated", path.name)


if __name__ == "__main__":
    fill(ROOT / "README.md")
    fill(ROOT / "MODEL_CARD.md")
