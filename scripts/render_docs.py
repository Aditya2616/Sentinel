"""Fill the generated result blocks in README.md, docs/RESULTS.md and MODEL_CARD.md from docs/data/eval.json.

    python scripts/render_docs.py

Blocks look like ``<!-- BEGIN:name -->`` ... ``<!-- END:name -->``; everything between the markers is replaced.
No number in those blocks is typed by hand.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "docs" / "data"
E = json.loads((DATA / "eval.json").read_text(encoding="utf-8"))
R = E["results"]
NL = chr(10)
LABEL = {
    "indist": "In-distribution test (neuralchemy + jackhhao)",
    "deepset": "deepset/prompt-injections (OOD, EN+DE)",
    "spml": "SPML OOD-test half",
    "hard_benign_v2": "Hard-benign v2 (frozen before the round-two models were run)",
    "hard_benign": "Hard-benign v1 (looked at once before the round-two re-selection)",
    "hard_benign_dedup": "Hard-benign v1, templated near-duplicates removed",
    "obfuscated": "Obfuscated attacks and benign",
    "attacks": "Plain attacks v1 (hand-written; informed the round-two rule fixes)",
    "attacks_v2": "Plain attacks v2 (hand-written, frozen beforehand)",
    "dolly_benign": "Everyday benign (Dolly-15k held out)",
    "indirect": "Indirect injection in documents (SYNTHETIC)",
}
LBL = E["meta"].get("system_labels", {})
SYS = {k: LBL[k] for k in ("rules_only", "tfidf", "protectai_default", "protectai", "classifier_alt", "classifier", "sentinel") if k in R and k in LBL}


def pc(x, d=1):
    return "n/a" if x is None else f"{x * 100:.{d}f}%"


def ci(pair):
    return "" if not pair else f" [{pair[0] * 100:.1f}, {pair[1] * 100:.1f}]"


def num(x, d=3):
    return "n/a" if x is None else f"{x:.{d}f}"


def _wil(e, key):
    iv = e.get(key)
    return f"{iv[0] * 100:.1f}% to {iv[1] * 100:.1f}%" if iv else "n/a"


def headline() -> str:
    s = R["sentinel"]
    preset = E["meta"].get("default_preset", "default")
    out = [f"| Headline (Sentinel, block decision, `{preset}` preset) | Value | 95% Wilson interval | Counts |", "|---|---|---|---|"]
    fp_rows = [
        ("False-positive rate, hard-benign **v2** (frozen, evaluated once)", "hard_benign_v2"),
        ("False-positive rate, hard-benign v1 (60 items; seen once before re-selection)", "hard_benign"),
        ("False-positive rate, hard-benign v1 with templated near-duplicates removed", "hard_benign_dedup"),
    ]
    for name, k in fp_rows:
        e = s[k]
        out.append(f"| {name} | {pc(e['fpr'])} | {_wil(e, 'fpr_ci')} | {e['confusion']['fp']} of {e['n_neg']} |")
    for name, k in (
        ("Recall on deepset/prompt-injections (out of distribution, untouched)", "deepset"),
        ("Recall on SPML OOD-test half", "spml"),
        ("Recall on plain attacks v2 (frozen)", "attacks_v2"),
    ):
        e = s[k]
        out.append(f"| {name} | {pc(e['recall'])} | {_wil(e, 'recall_ci')} | {e['confusion']['tp']} of {e['n_pos']} |")
    e = s["dolly_benign"]
    out.append(f"| False-positive rate on everyday benign (Dolly-15k held out) | {pc(e['fpr'])} | {_wil(e, 'fpr_ci')} | {e['confusion']['fp']} of {e['n_neg']} |")
    d = s["deepset"]
    out.append(f"| Recall on deepset counting a flag as a catch (flagged prompts still reach the model) | {pc(d['alert']['recall'])} | | n={d['n_pos']} attacks |")
    i = s["indist"]
    out.append(f"| In-distribution F1 (secondary; the training data is partly synthetic) | {num(i['f1'])} | | n={i['n']} |")
    return NL.join(out)


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
    return NL.join(out)


def language() -> str:
    out = ["| deepset subset | n | attacks | Recall (Sentinel) | FPR (Sentinel) | Recall (classifier only) |", "|---|---|---|---|---|---|"]
    for lg, e in E["deepset_by_language"].items():
        out.append(f"| {lg.upper()} | {e['n']} | {e['n_pos']} | {pc(e['recall'])} | {pc(e['fpr'])} | {pc(e['classifier_only']['recall'])} |")
    return NL.join(out)


def latency() -> str:
    L = E["latency"]
    rows = [("Rules only", "rules_only"), ("Classifier, one prompt at a time", "classifier_single"), ("Full Sentinel, one prompt", "sentinel_full"), ("TF-IDF + LR", "tfidf")]
    out = ["| Path | p50 (ms) | p95 (ms) |", "|---|---|---|"]
    for lab, k in rows:
        out.append(f"| {lab} | {L[k]['p50_ms']:.1f} | {L[k]['p95_ms']:.1f} |")
    out.append(f"{NL}CPU, classifier in batches of 64: {L['classifier_batch64_ms_per_prompt']:.1f} ms per prompt. {L['note']}")
    g = L.get("gpu")
    if g:
        out.append(
            f"{NL}GPU ({g['device']}, float32) for comparison: classifier {g['classifier_single']['p50_ms']:.1f} ms p50 / {g['classifier_single']['p95_ms']:.1f} ms p95 per prompt, "
            f"full Sentinel {g['sentinel_full']['p50_ms']:.1f} / {g['sentinel_full']['p95_ms']:.1f} ms, batches of 64: {g['classifier_batch64_ms_per_prompt']:.1f} ms per prompt."
        )
    return NL.join(out)


def thresholds() -> str:
    m = E["meta"]
    out = [
        f"Chosen on the validation split only. Rule, fixed before the round-two models were trained: the block threshold is the lowest threshold whose validation false-positive rate is within the caps below on "
        f"hard-benign text (n={m['val_hard_benign_n']}) and on everyday benign text; the flag threshold uses looser caps. `{m['default_preset']}` is the default; "
        "select another with the `SENTINEL_PRESET` environment variable or `Sentinel.load(preset=...)`.",
        "",
        "| Preset | Block caps (hard-benign / everyday val FPR) | Flag caps | Block threshold | Flag threshold | Rules may block alone |",
        "|---|---|---|---|---|---|",
    ]
    caps = {"strict": ("1%", "0.5%", "5%", "2%"), "balanced": ("2%", "0.5%", "10%", "2%"), "permissive": ("5%", "1%", "20%", "3%")}
    for name, t in m["presets"].items():
        c = caps[name]
        out.append(f"| {name}{' (default)' if name == m['default_preset'] else ''} | {c[0]} / {c[1]} | {c[2]} / {c[3]} | {t['t_block']:.3f} | {t['t_flag']:.3f} | {t['rule_block_high']} |")
    return NL.join(out)


def presets() -> str:
    PR = E["preset_results"]
    sets = [("deepset", "deepset recall"), ("spml", "SPML OOD-test recall"), ("attacks_v2", "plain v2 recall")]
    fsets = [("hard_benign_v2", "hard-benign v2"), ("hard_benign", "v1"), ("hard_benign_dedup", "v1 distinct"), ("dolly_benign", "everyday")]
    out = ["| Preset | " + " | ".join(f"{label} (block / flag or block)" for _, label in sets) + " | " + " | ".join(f"FPR {label}" for _, label in fsets) + " |", "|---|" + "---|" * (len(sets) + len(fsets))]
    for name, pr in PR.items():
        cells = [f"{pc(pr['sets'][k]['recall_block'], 0)} / {pc(pr['sets'][k]['recall_flag_or_block'], 0)}" for k, _ in sets]
        cells += [f"{pc(pr['sets'][k]['fpr_block'])} ({pr['sets'][k]['fp']}/{pr['sets'][k]['n_neg']})" for k, _ in fsets]
        out.append(f"| {name}{' (default)' if name == E['meta']['default_preset'] else ''} | " + " | ".join(cells) + " |")
    return NL.join(out)


def _train_lines(tl: dict, title: str) -> list[str]:
    where = f"{tl.get('gpu') or 'CPU'} ({tl.get('device', 'cpu')}, float32)"
    lines = [
        f"- **{title}: `{tl['base_model']}`** on {where}: {tl['n_train']} training rows, {tl['n_val']} validation rows; "
        f"{tl['args']['epochs']} epochs at most, lr {tl['args']['lr']}, batch {tl['args']['batch_size']}, max length {tl['args']['max_length']}, seed {tl['args']['seed']}; "
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
            "- Selection rule, fixed before the round-two models were trained: each model gets its `balanced` block threshold (validation hard-benign FPR at most 2%, everyday-benign at most 0.5%); "
            "the model with the best OOD-dev recall at that threshold is the default. See the selection table."
        )
    for bench in sorted(DATA.glob("cpu_train_bench*.json")):
        b = json.loads(bench.read_text(encoding="utf-8"))
        lines.append(
            f"- CPU training time, **estimate** for `{b['base']}`: `scripts/bench_cpu_train.py` timed {b['steps_timed']} real steps at {b['seconds_per_step']} s/step with {b['threads']} threads "
            f"({b['cpu_count']} logical cores; {b['load']}), which extrapolates to about {b['estimated_minutes_for_full_run']} minutes for {b['epochs']} epochs ({b['steps_per_run']} steps), "
            "excluding validation passes. It is an extrapolation, and a busier machine is slower."
        )
    sizes = m["build_report"]["sizes"]
    hn = sum(1 for ln in (ROOT / "data" / "hand_written" / "hard_neg_train.jsonl").read_text(encoding="utf-8").split(NL) if ln.strip())
    reps = int(values()["hn_repeat"])
    if sizes["train"]["n"] + hn * (reps - 1) != m["training_log"]["n_train"]:
        raise ValueError("training-row arithmetic no longer adds up; fix the README sentence generator")
    lines.append(
        f"- Training rows: {sizes['train']['n']} de-duplicated rows plus {hn} hard-benign rows repeated {reps - 1} extra times ({reps} copies in total) gives {m['training_log']['n_train']} training rows."
    )
    lines.append("- Split sizes after de-duplication: " + ", ".join(f"{k} {v['n']} ({v['malicious']} attacks)" for k, v in sizes.items()) + ".")
    return NL.join(lines)


def shortcuts() -> str:
    s = E["shortcuts"]
    a = ", ".join(f"{k} {num(v, 2)}" for k, v in s["length_only_roc_auc"].items())
    b = ", ".join(f"{k} {num(v, 2)}" for k, v in s["label_shuffled_tfidf_roc_auc"].items())
    return f"- Length-only logistic regression, ROC-AUC: {a} (0.50 is chance).{NL}- TF-IDF trained on shuffled labels, ROC-AUC: {b} (should be near 0.50)."


def operating() -> str:
    """Per model: the thresholds giving 1, 2 and 5% FPR on the validation hard-benign set, and what they do on every test set."""
    OP = E["operating_table"]
    recs = [("deepset", "deepset"), ("spml", "SPML test"), ("indist", "in-dist"), ("attacks_v2", "plain v2"), ("obfuscated", "obfuscated"), ("indirect", "indirect (synth.)")]
    fprs = [("hard_benign_v2", "hard v2"), ("hard_benign", "hard v1"), ("hard_benign_dedup", "v1 distinct"), ("dolly_benign", "everyday")]
    head = "| Model | Val hard-benign FPR | Threshold | " + " | ".join(f"Recall {label}" for _, label in recs) + " | " + " | ".join(f"FPR {label}" for _, label in fprs) + " |"
    out = [head, "|---|---|---|" + "---|" * (len(recs) + len(fprs))]
    for sk in ("classifier", "classifier_alt", "tfidf"):
        if sk not in OP["systems"]:
            continue
        for lv in OP["levels"]:
            cell = OP["systems"][sk][str(lv)]
            r = [pc(cell["recall"][k]["v"], 0) if k in cell["recall"] else "n/a" for k, _ in recs]
            f = [f"{pc(cell['fpr'][k]['v'])} ({cell['fpr'][k]['k']}/{cell['fpr'][k]['n']})" if k in cell["fpr"] else "n/a" for k, _ in fprs]
            name = LBL[sk] if lv == OP["levels"][0] else ""
            out.append(f"| {name} | {lv * 100:.0f}% | {cell['threshold']:.3f} | " + " | ".join(r) + " | " + " | ".join(f) + " |")
    return NL.join(out)


def _load(name: str) -> dict:
    p = DATA / name
    return json.loads(p.read_text(encoding="utf-8"))["results"]["sentinel"] if p.exists() else {}


def before_after() -> str:
    """The first model, round one as published, and round two, on the same current test splits."""
    B1, B2, A = _load("baseline_v1.json"), _load("baseline_round1.json"), R["sentinel"]

    def cell(B, n, k):
        return pc(B[n][k]) if n in B and B[n].get(k) is not None else "not run"

    def acell(B, n):
        return pc(B[n]["alert"]["recall"]) if n in B and "alert" in B[n] else "not run"

    def fc(B, n):
        return f"{pc(B[n]['fpr'])} ({B[n]['confusion']['fp']}/{B[n]['n_neg']})" if n in B else "not run"

    rows = [
        ("deepset", "deepset (OOD, untouched)"), ("spml", "SPML OOD-test"), ("spml_dev", "SPML OOD-dev (selection only)"), ("indist", "In-distribution"),
        ("obfuscated", "Obfuscated"), ("attacks", "Plain attacks v1"), ("attacks_v2", "Plain attacks v2 (frozen)"), ("indirect", "Indirect (SYNTHETIC)"),
    ]
    out = ["| Set | Recall (block): first model | round 1 | round 2 | Recall (flag or block): first | round 1 | round 2 |", "|---|---|---|---|---|---|---|"]
    for n, lab in rows:
        out.append(f"| {lab} | {cell(B1, n, 'recall')} | {cell(B2, n, 'recall')} | {pc(A[n]['recall'])} | {acell(B1, n)} | {acell(B2, n)} | {pc(A[n]['alert']['recall'])} |")
    out += ["", "| Benign side | FPR (block): first model | round 1 | round 2 | n |", "|---|---|---|---|---|"]
    for n, lab in [
        ("hard_benign_v2", "Hard-benign v2 (frozen)"), ("hard_benign", "Hard-benign v1 (seen once)"), ("hard_benign_dedup", "Hard-benign v1, distinct items"),
        ("dolly_benign", "Everyday (Dolly-15k held out)"), ("spml", "SPML OOD-test benign"), ("deepset", "deepset benign"),
    ]:
        out.append(f"| {lab} | {fc(B1, n)} | {fc(B2, n)} | {fc(A, n)} | {A[n]['n_neg']} |")
    return NL.join(out)


def ablation() -> str:
    p = DATA / "ablation.json"
    if not p.exists():
        return "No ablation recorded."
    rows = json.loads(p.read_text(encoding="utf-8"))
    head = (
        "| Model (round two, same training data) | Train rows | Epochs run | Val PR-AUC | OOD-dev PR-AUC | Balanced block threshold | OOD-dev recall at it | OOD-dev FPR | "
        "Val hard-benign FPR | Val everyday FPR | OOD-dev recall at 1% / 2% / 5% hard-benign val FPR | Selected |"
    )
    out = [head, "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        at = r["dev_recall_at_hard_benign_val_fpr"]
        out.append(
            f"| {r['variant']} | {r['train_rows']} | {r['epochs_run']} | {r['val_pr_auc']:.4f} | {r['dev_pr_auc']:.4f} | {r['balanced_block_threshold']:.3f} | {pc(r['dev_recall_at_balanced'])} | "
            f"{pc(r['dev_fpr_at_balanced'])} | {pc(r['val_hard_benign_fpr_at_balanced'])} (n={r['val_hard_benign_n']}) | {pc(r['val_everyday_fpr_at_balanced'])} | "
            f"{pc(at['0.01'], 0)} / {pc(at['0.02'], 0)} / {pc(at['0.05'], 0)} | {'yes' if r['selected'] else ''} |"
        )
    return NL.join(out)


def ablation_round1() -> str:
    p = DATA / "ablation_round1.json"
    if not p.exists():
        return "No round-one ablation recorded."
    rows = json.loads(p.read_text(encoding="utf-8"))
    head = "| Variant (round one; selection used validation + OOD-dev only) | Train rows | Epochs run | Val PR-AUC | OOD-dev PR-AUC | OOD-dev recall @ val 1% FPR | OOD-dev FPR | Val hard-benign FPR (19 items) |"
    out = [head, "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        out.append(
            f"| {r['variant']} | {r['train_rows']} | {r['epochs_run']} | {r['val_pr_auc']:.4f} | {r['dev_pr_auc']:.4f} | {pc(r['dev_recall_at_that_threshold'])} | "
            f"{pc(r['dev_fpr_at_that_threshold'])} | {pc(r['val_hard_benign_fpr_at_that_threshold'])} |"
        )
    return NL.join(out)


def errors() -> str:
    e = E["errors"]
    skip = ("spml_dev", "hard_benign_dedup")
    sets = [n for n in R["sentinel"] if n not in skip]
    fp = sum(R["sentinel"][n]["confusion"]["fp"] for n in sets)
    missed = sum(R["sentinel"][n]["alert"]["confusion"]["fn"] for n in sets if "alert" in R["sentinel"][n])
    return (
        f"Across the reported test sets (OOD-dev and the de-duplicated v1 subset excluded), Sentinel blocked {fp} benign prompts and let {missed} attacks through without even a flag. "
        f"Up to 60 examples of each are stored in `docs/data/eval.json` under `errors` ({len(e['false_positives'])} and {len(e['false_negatives'])} stored)."
    )


def protectai() -> str:
    """The zero-shot public detector beside Sentinel, same sets, same device and dtype (float32, GPU)."""
    if "protectai" not in R:
        return "Not run in this evaluation."
    rows = [("indist", "In-distribution"), ("deepset", "deepset (OOD)"), ("spml", "SPML OOD-test"), ("attacks_v2", "Plain attacks v2"), ("obfuscated", "Obfuscated"), ("indirect", "Indirect (SYNTHETIC)")]
    brows = [("hard_benign_v2", "Hard-benign v2"), ("hard_benign", "Hard-benign v1"), ("hard_benign_dedup", "Hard-benign v1, distinct"), ("dolly_benign", "Everyday benign"), ("deepset", "deepset benign"), ("spml", "SPML benign")]
    keys = ("sentinel", "classifier", "protectai_default", "protectai")
    out = ["| Attack set (recall) | " + " | ".join(LBL[k] for k in keys) + " |", "|---|" + "---|" * len(keys)]
    for n, lab in rows:
        out.append(f"| {lab} | " + " | ".join(pc(R[k][n]["recall"]) for k in keys) + " |")
    out += ["", "| Benign set (false-positive rate) | " + " | ".join(LBL[k] for k in keys) + " |", "|---|" + "---|" * len(keys)]
    for n, lab in brows:
        out.append(f"| {lab} | " + " | ".join(f"{pc(R[k][n]['fpr'])} ({R[k][n]['confusion']['fp']}/{R[k][n]['n_neg']})" for k in keys) + " |")
    return NL.join(out)


def values() -> dict[str, str]:
    """Every number quoted in prose, computed from the results and data files. Prose uses <!--v:key-->text<!--/v-->."""
    import sys

    sys.path.insert(0, str(ROOT / "src"))
    from sentinel.evaluate import PRESET_CAPS

    S, M = R["sentinel"], E["meta"]
    B1, B2 = _load("baseline_v1.json"), _load("baseline_round1.json")
    hand = ROOT / "data" / "hand_written"

    def lines(name: str) -> int:
        return sum(1 for ln in (hand / name).read_text(encoding="utf-8").split(NL) if ln.strip())

    def cnt(B, n, k="fp"):
        return str(B[n]["confusion"][k])

    tl, al = M["training_log"], M.get("alt_training_log") or {}
    train_py = (ROOT / "src" / "sentinel" / "train.py").read_text(encoding="utf-8")
    cap = PRESET_CAPS["balanced"]["block"]
    ops = E["operating_table"]["levels"]
    pre = R.get("protectai")
    return {
        "n_rules": str(len(json.loads((DATA / "rules.json").read_text(encoding="utf-8")))),
        "first_ood_range": f"{B1['deepset']['recall'] * 100:.0f} to {B1['spml']['recall'] * 100:.0f}%",
        "val_hb_old": str(lines("hard_benign_val.jsonl")),
        "val_hb_new": str(lines("hard_neg_val.jsonl")),
        "val_hb_total": str(M["val_hard_benign_n"]),
        "hn_train_n": str(lines("hard_neg_train.jsonl")),
        "hn_repeat": re.search(r"hw_hn_train=(\d+)", train_py).group(1),
        "hb_v1_n": str(S["hard_benign"]["n"]),
        "hb_v1_distinct_n": str(S["hard_benign_dedup"]["n"]),
        "hb_v2_n": str(S["hard_benign_v2"]["n"]),
        "att_v1_n": str(S["attacks"]["n"]),
        "att_v2_n": str(S["attacks_v2"]["n"]),
        "r1_v1_fpr": pc(B2["hard_benign"]["fpr"]),
        "r1_v1_fp": cnt(B2, "hard_benign"),
        "r1_dedup_fp": cnt(B2, "hard_benign_dedup"),
        "r1_v2_fpr": pc(B2["hard_benign_v2"]["fpr"]),
        "r1_v2_fp": cnt(B2, "hard_benign_v2"),
        "r2_v2_fpr": pc(S["hard_benign_v2"]["fpr"]),
        "r2_v2_fp": cnt(S, "hard_benign_v2"),
        "r2_v1_fp": cnt(S, "hard_benign"),
        "plain_first": pc(B1["attacks"]["recall"]),
        "plain_first_tp": cnt(B1, "attacks", "tp"),
        "plain_r1": pc(B2["attacks"]["recall"]),
        "plain_r1_tp": cnt(B2, "attacks", "tp"),
        "plain_r1_missed": cnt(B2, "attacks", "fn"),
        "plain_r2": pc(S["attacks"]["recall"]),
        "cap_hb": f"{cap[0] * 100:g}%",
        "cap_dolly": f"{cap[1] * 100:g}%",
        "levels": ", ".join(f"{x * 100:g}%" for x in ops[:-1]) + f" and {ops[-1] * 100:g}%",
        "hb_v2_fpr0": pc(S["hard_benign_v2"]["fpr"], 0),
        "deepset_block": pc(S["deepset"]["recall"], 0),
        "spml_block": pc(S["spml"]["recall"], 0),
        "deepset_flag": pc(S["deepset"]["alert"]["recall"], 0),
        "spml_flag": pc(S["spml"]["alert"]["recall"], 0),
        "pre_spml_default": pc(R["protectai_default"]["spml"]["recall"], 0) if pre else "n/a",
        "pre_spml_balanced": pc(pre["spml"]["recall"], 0) if pre else "n/a",
        "pre_hb_v2_default": pc(R["protectai_default"]["hard_benign_v2"]["fpr"], 0) if pre else "n/a",
        "pre_hb_v2_balanced": pc(pre["hard_benign_v2"]["fpr"], 1) if pre else "n/a",
        "r2_spml_fpr_note": pc(S["spml"]["fpr"], 1),
        "params_default": f"{M['n_params']['classifier'] / 1e6:.1f}M",
        "params_alt": f"{M['n_params']['classifier_alt'] / 1e6:.1f}M",
        "params_protectai": f"{M['n_params'].get('protectai', 0) / 1e6:.0f}M",
        "protectai_rev": (M.get("external_comparison") or {}).get("revision", "")[:8],
        "max_len": str(tl["args"]["max_length"]),
        "lr_default": f"{tl['args']['lr']:g}",
        "lr_alt": f"{al.get('args', {}).get('lr', 0):g}",
        "epochs_max": str(tl["args"]["epochs"]),
        "batch": str(tl["args"]["batch_size"]),
    }


MARK = re.compile(r"<!--v:(\w+)-->(.*?)<!--/v-->", re.S)


def substitute(s: str) -> str:
    v = values()

    def sub(m: re.Match) -> str:
        if m.group(1) not in v:
            raise KeyError(f"unknown value key {m.group(1)!r}")
        return f"<!--v:{m.group(1)}-->{v[m.group(1)]}<!--/v-->"

    return MARK.sub(sub, s)


BLOCKS = {
    "protectai": protectai,
    "headline": headline, "per_set": per_set, "language": language, "latency": latency, "thresholds": thresholds, "presets": presets, "training": training,
    "shortcuts": shortcuts, "errors": errors, "operating": operating, "before_after": before_after, "ablation": ablation, "ablation_round1": ablation_round1,
}


def render(text: str) -> str:
    for name, fn in BLOCKS.items():
        pat = re.compile(rf"(<!-- BEGIN:{name} -->)(.*?)(<!-- END:{name} -->)", re.S)
        body = fn()
        text = pat.sub(lambda m, body=body: f"{m.group(1)}{NL}{body}{NL}{m.group(3)}", text)
    return substitute(text)


DOCS = [ROOT / "README.md", ROOT / "docs" / "RESULTS.md", ROOT / "MODEL_CARD.md"]


def fill(path: Path) -> None:
    if path.exists():
        path.write_text(render(path.read_text(encoding="utf-8")), encoding="utf-8", newline=NL)
        print("updated", path.name)


def check() -> list[str]:
    """Names of documents whose generated blocks or quoted numbers differ from the results files."""
    bad = []
    for path in DOCS:
        if path.exists() and render(path.read_text(encoding="utf-8").replace(chr(13) + NL, NL)) != path.read_text(encoding="utf-8").replace(chr(13) + NL, NL):
            bad.append(path.name)
    return bad


if __name__ == "__main__":
    import sys

    if "--check" in sys.argv:
        out_of_sync = check()
        print("out of sync: " + ", ".join(out_of_sync) + " (run python scripts/render_docs.py)" if out_of_sync else "documents are in sync with docs/data")
        sys.exit(1 if out_of_sync else 0)
    for d in DOCS:
        fill(d)
