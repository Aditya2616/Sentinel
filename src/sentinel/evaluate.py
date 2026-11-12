"""Full evaluation: every system on every test set, thresholds chosen on validation only.

    sentinel eval                    # writes docs/data/eval.json, docs/data/stream.json, docs/data/rules.json

Scores are cached under runs/scores/ so re-running is cheap; --refresh recomputes them.
"""

from __future__ import annotations

import argparse
import json
import platform
import time
from pathlib import Path

import numpy as np

from . import data as D
from .baseline import TfidfBaseline
from .decision import Thresholds
from .metrics import (
    auc_roc,
    average_precision,
    confusion,
    pr_curve,
    prf,
    reliability,
    roc_curve,
    threshold_at_fpr,
)
from .rules import rule_catalogue, scan
from .screen import Sentinel

ROOT = D.ROOT
OUT = ROOT / "docs" / "data"
SCORES = ROOT / "runs" / "scores"
TEST_SETS = ["indist", "deepset", "spml", "hard_benign", "obfuscated", "attacks", "dolly_benign", "indirect"]
SET_LABEL = {
    "indist": "In-distribution (neuralchemy + jackhhao test, de-duplicated)",
    "deepset": "OOD: deepset/prompt-injections (EN + DE)",
    "spml": "OOD: SPML chatbot prompts (subsample)",
    "hard_benign": "Hard benign: talks about injection (hand-written)",
    "obfuscated": "Obfuscated attacks + obfuscated benign (hand-written)",
    "attacks": "Plain attacks (hand-written)",
    "dolly_benign": "Everyday benign (Dolly-15k held-out)",
    "indirect": "Indirect injection in documents (SYNTHETIC, small)",
}


def _src(name: str) -> str:
    return "document" if name == "indirect" else "user"


def _cached(key: str, fn, refresh: bool, n: int) -> np.ndarray:
    SCORES.mkdir(parents=True, exist_ok=True)
    p = SCORES / f"{key}.npy"
    if p.exists() and not refresh:
        arr = np.load(p)
        if len(arr) == n:
            return arr
    arr = np.asarray(fn(), dtype=float)
    np.save(p, arr)
    return arr


def choose_thresholds(val_y: np.ndarray, val_s: np.ndarray, val_decide_fn) -> tuple[Thresholds, dict]:
    """Operating points from the validation split only: block at 1% FPR, flag at 3%, agreement at 10%."""
    t_block = threshold_at_fpr(val_y, val_s, 0.01)
    t_flag = min(t_block, threshold_at_fpr(val_y, val_s, 0.03))
    t_agree = min(t_flag, threshold_at_fpr(val_y, val_s, 0.10))
    best, info = None, {}
    for rbh in (True, False):
        th = Thresholds(t_flag=t_flag, t_block=t_block, t_agree=t_agree, rule_block_high=rbh)
        pred = val_decide_fn(th)
        c = confusion(val_y, np.array([a == "block" for a in pred]))
        m = prf(c)
        info[f"rule_block_high={rbh}"] = {"f1": m["f1"], "fpr": m["fpr"], "recall": m["recall"]}
        # prefer the policy with the higher validation F1; ties go to letting rules block (the safer default)
        if best is None or m["f1"] > best[1] + 1e-9:
            best = (th, m["f1"])
    return best[0], info


def _latency(fn, items: list[str], reps: int = 1) -> dict:
    ts = []
    for t in items:
        t0 = time.perf_counter()
        for _ in range(reps):
            fn(t)
        ts.append((time.perf_counter() - t0) / reps * 1000)
    a = np.array(ts)
    return {"n": len(a), "p50_ms": float(np.percentile(a, 50)), "p95_ms": float(np.percentile(a, 95)), "mean_ms": float(a.mean())}


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Evaluate Sentinel and baselines")
    ap.add_argument("--model-dir", default="models/sentinel-minilm")
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--threads", type=int, default=6)
    ap.add_argument("--latency-n", type=int, default=150)
    a = ap.parse_args(argv)

    import torch

    torch.set_num_threads(a.threads)
    from .classifier import TransformerClassifier

    model_dir = Path(a.model_dir)
    clf = TransformerClassifier(model_dir, threads=a.threads)
    val = D.load("val")
    train = D.load("train")
    tests = {n: D.load(f"test_{n}") for n in TEST_SETS}
    Y = {n: np.array([r["label"] for r in rows]) for n, rows in tests.items()}
    T = {n: [r["text"] for r in rows] for n, rows in tests.items()}
    val_y, val_t = np.array([r["label"] for r in val]), [r["text"] for r in val]
    refresh = a.refresh

    systems: dict[str, dict[str, np.ndarray]] = {}  # system -> set -> score
    val_scores: dict[str, np.ndarray] = {}

    # --- fine-tuned classifier (calibrated probability)
    print("scoring classifier", flush=True)
    val_scores["classifier"] = _cached("clf__val", lambda: clf.score(val_t), refresh, len(val_t))
    systems["classifier"] = {n: _cached(f"clf__{n}", lambda n=n: clf.score(T[n]), refresh, len(T[n])) for n in TEST_SETS}

    # --- TF-IDF baseline
    print("fitting tfidf", flush=True)
    base = TfidfBaseline().fit([r["text"] for r in train], [r["label"] for r in train])
    val_scores["tfidf"] = base.score(val_t)
    systems["tfidf"] = {n: base.score(T[n]) for n in TEST_SETS}

    # --- shortcut checks
    from sklearn.linear_model import LogisticRegression

    Ltr = np.log1p([len(r["text"]) for r in train]).reshape(-1, 1)
    lenclf = LogisticRegression().fit(Ltr, [r["label"] for r in train])
    length_only = {n: lenclf.predict_proba(np.log1p([len(t) for t in T[n]]).reshape(-1, 1))[:, 1] for n in TEST_SETS}
    rng = np.random.default_rng(0)
    shuffled = TfidfBaseline().fit([r["text"] for r in train], list(rng.permutation([r["label"] for r in train])))
    shuffled_scores = {n: shuffled.score(T[n]) for n in ("indist", "deepset")}
    shortcuts = {
        "length_only_roc_auc": {n: auc_roc(Y[n], length_only[n]) for n in ("indist", "deepset", "spml")},
        "label_shuffled_tfidf_roc_auc": {n: auc_roc(Y[n], shuffled_scores[n]) for n in shuffled_scores},
    }

    # --- thresholds on validation only
    sent = Sentinel(clf, Thresholds())

    def val_decide(th: Thresholds):
        sent.thresholds = th
        return [d.action for d in sent.screen_batch(val_t)]

    th, policy_info = choose_thresholds(val_y, val_scores["classifier"], val_decide)
    sent.thresholds = th
    (model_dir / "thresholds.json").write_text(json.dumps(th.to_dict(), indent=2))
    print("thresholds", th, policy_info, flush=True)
    sys_thr = {s: threshold_at_fpr(val_y, val_scores[s], 0.01) for s in val_scores}

    # --- full Sentinel pipeline decisions
    print("running full pipeline", flush=True)
    decisions = {n: sent.screen_batch(T[n], _src(n)) for n in TEST_SETS}
    rules_only = Sentinel(None, th)
    rules_dec = {n: rules_only.screen_batch(T[n], _src(n)) for n in TEST_SETS}

    # --- assemble results
    results: dict[str, dict[str, dict]] = {}

    def put(system: str, n: str, block: np.ndarray, score: np.ndarray | None, thr: float | None, alert: np.ndarray | None = None):
        y = Y[n]
        c = confusion(y, block)
        entry = {"n": int(len(y)), "n_pos": int(y.sum()), "n_neg": int((1 - y).sum()), "confusion": c, **prf(c)}
        from .metrics import wilson

        if entry["n_neg"]:
            entry["fpr_ci"] = wilson(c["fp"], entry["n_neg"])
        if entry["n_pos"]:
            entry["recall_ci"] = wilson(c["tp"], entry["n_pos"])
        if score is not None and entry["n_pos"] and entry["n_neg"]:
            entry["roc_auc"] = auc_roc(y, score)
            entry["pr_auc"] = average_precision(y, score)
        if thr is not None:
            entry["threshold"] = float(thr)
        if alert is not None:
            ca = confusion(y, alert)
            entry["alert"] = {"confusion": ca, **prf(ca)}
        results.setdefault(system, {})[n] = entry

    for n in TEST_SETS:
        blk = np.array([d.action == "block" for d in decisions[n]])
        alr = np.array([d.action != "allow" for d in decisions[n]])
        sc = np.array([d.score for d in decisions[n]], dtype=float)
        put("sentinel", n, blk, systems["classifier"][n], None, alr)
        rb = np.array([d.action == "block" for d in rules_dec[n]])
        ra = np.array([d.action != "allow" for d in rules_dec[n]])
        put("rules_only", n, rb, None, None, ra)
        put("classifier", n, systems["classifier"][n] >= th.t_block, systems["classifier"][n], th.t_block)
        put("tfidf", n, systems["tfidf"][n] >= sys_thr["tfidf"], systems["tfidf"][n], sys_thr["tfidf"])
        del sc

    # --- curves for classifier-style systems on the pooled "scored" sets
    curves = {}
    for n in ("indist", "deepset", "spml"):
        curves[n] = {}
        for s in systems:
            curves[n][s] = {"roc": roc_curve(Y[n], systems[s][n]), "pr": pr_curve(Y[n], systems[s][n])}
    pooled_n = ["indist", "deepset", "spml", "hard_benign", "obfuscated", "attacks", "dolly_benign"]
    py = np.concatenate([Y[n] for n in pooled_n])
    ps = {s: np.concatenate([systems[s][n] for n in pooled_n]) for s in systems}
    curves["pooled"] = {s: {"roc": roc_curve(py, ps[s]), "pr": pr_curve(py, ps[s])} for s in systems}
    pooled_conf = {"n": int(len(py)), "n_pos": int(py.sum())}

    # --- deepset by language
    langs = np.array([r.get("lang", "en") for r in tests["deepset"]])
    by_lang = {}
    for lg in ("en", "de"):
        m = langs == lg
        if m.sum():
            blk = np.array([d.action == "block" for d in decisions["deepset"]])[m]
            by_lang[lg] = {"n": int(m.sum()), "n_pos": int(Y["deepset"][m].sum()), **prf(confusion(Y["deepset"][m], blk)), "confusion": confusion(Y["deepset"][m], blk),
                           "classifier_only": prf(confusion(Y["deepset"][m], systems["classifier"]["deepset"][m] >= th.t_block))}

    # --- per-category recall on in-distribution test
    cats: dict[str, dict] = {}
    for r, d, s in zip(tests["indist"], decisions["indist"], systems["classifier"]["indist"], strict=True):
        if r["label"] == 1:
            c = cats.setdefault(r.get("category", "?"), {"n": 0, "blocked": 0, "classifier_blocked": 0})
            c["n"] += 1
            c["blocked"] += int(d.action == "block")
            c["classifier_blocked"] += int(s >= th.t_block)

    # --- calibration
    cal = {"val": reliability(val_y, val_scores["classifier"]), "indist": reliability(Y["indist"], systems["classifier"]["indist"])}

    # --- errors worth showing (truncated)
    errors = {"false_positives": [], "false_negatives": []}
    for n in TEST_SETS:
        for r, d in zip(tests[n], decisions[n], strict=True):
            row = {"set": n, "text": r["text"][:220], "score": d.score, "action": d.action, "rules": sorted({h.rule_id for h in d.hits}), "category": r.get("category")}
            if r["label"] == 0 and d.action == "block":
                errors["false_positives"].append(row)
            if r["label"] == 1 and d.action == "allow":
                errors["false_negatives"].append(row)
    errors["false_positives"] = errors["false_positives"][:60]
    errors["false_negatives"] = errors["false_negatives"][:60]

    # --- latency on this CPU (machine was shared with other jobs: noted in the output)
    print("measuring latency", flush=True)
    pool = [r["text"] for n in ("dolly_benign", "hard_benign", "attacks", "indist", "deepset") for r in tests[n]]
    rs = np.random.RandomState(5)
    lat_items = [pool[i] for i in rs.choice(len(pool), min(a.latency_n, len(pool)), replace=False)]
    for t in lat_items[:5]:
        sent.screen(t, log=False)
    latency = {
        "rules_only": _latency(lambda t: scan(t), lat_items),
        "classifier_single": _latency(lambda t: clf.score([t]), lat_items),
        "sentinel_full": _latency(lambda t: sent.screen(t, log=False), lat_items),
        "tfidf": _latency(lambda t: base.score([t]), lat_items),
        "threads": a.threads,
        "cpu": platform.processor(),
        "note": "Measured on a Windows 11 desktop CPU that was shared with other running jobs, so treat as an upper-bound ballpark.",
    }
    t0 = time.perf_counter()
    clf.score(lat_items[:64])
    latency["classifier_batch64_ms_per_prompt"] = (time.perf_counter() - t0) / 64 * 1000

    # --- stored scores for the threshold slider in the UI (rounded, compact)
    slider = {n: {"y": Y[n].tolist(), "s": [round(float(x), 3) for x in systems["classifier"][n]]} for n in pooled_n}

    # --- recorded stream for the static demo
    stream = build_stream(tests, decisions, th)

    meta = {
        "generated": time.strftime("%Y-%m-%d"),
        "thresholds": th.to_dict(),
        "threshold_selection": {"policy_comparison_on_val": policy_info, "val_n": int(len(val_y)), "val_fpr_targets": {"block": 0.01, "flag": 0.03, "agree": 0.10}},
        "baseline_thresholds_at_1pct_val_fpr": sys_thr,
        "model": clf.name,
        "training_log": json.loads((model_dir / "training_log.json").read_text()) if (model_dir / "training_log.json").exists() else None,
        "sources": D.SOURCES,
        "build_report": json.loads((D.PROCESSED / "build_report.json").read_text()),
        "set_labels": SET_LABEL,
        "pooled": pooled_conf,
    }
    out = {"meta": meta, "results": results, "curves": curves, "deepset_by_language": by_lang, "per_category_recall_indist": cats, "calibration": cal, "shortcuts": shortcuts, "errors": errors, "latency": latency, "slider": slider}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "eval.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":"), default=float), encoding="utf-8")
    (OUT / "stream.json").write_text(json.dumps(stream, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (OUT / "rules.json").write_text(json.dumps(rule_catalogue(), indent=1), encoding="utf-8")
    print_summary(results)


SAFE_CATEGORIES = {
    "direct_injection", "instruction_override", "prompt_extraction", "prompt_leak", "system_extraction", "persona_replacement",
    "rag_poisoning", "indirect_injection", "context_confusion", "output_manipulation", "response_manipulation", "prompt_injection",
    "system_manipulation", "benign", "control", "edge_case", "jailbreak", "dolly_benign", "hard_benign",
}


def build_stream(tests, decisions, th: Thresholds, per_set: dict | None = None) -> dict:
    """A fixed, seeded sample of real evaluation items and the decisions Sentinel made on them."""
    per_set = per_set or {"hard_benign": 40, "attacks": 20, "obfuscated": 24, "indist": 50, "deepset": 40, "spml": 30, "dolly_benign": 30, "indirect": 24}
    rs = np.random.RandomState(11)
    items = []
    for n, k in per_set.items():
        idx = [i for i, r in enumerate(tests[n]) if len(r["text"]) <= 260 or n == "indirect"]
        if n in ("indist",):
            idx = [i for i in idx if tests[n][i].get("category") in SAFE_CATEGORIES and tests[n][i].get("source") not in ("harmbench", "wildguard_judgecomp")]
        if n == "deepset":
            idx = [i for i in idx if tests[n][i].get("lang", "en") == "en" or rs.rand() < 0.35]
        take = rs.choice(idx, min(k, len(idx)), replace=False)
        for i in take:
            r, d = tests[n][i], decisions[n][i]
            text = r["text"] if n != "indirect" else r["text"][:420]
            if any(ord(c) >= 0xE0000 for c in text):  # keep invisible tag characters out of the page; the rules still saw them
                text = "".join(c for c in text if ord(c) < 0xE0000) + "  [+ hidden Unicode tag text]"
            items.append(
                {
                    "set": n,
                    "text": text,
                    "label": int(r["label"]),
                    "action": d.action,
                    "score": None if d.score is None else round(d.score, 3),
                    "rules": [{"id": h.rule_id, "sev": h.severity, "cat": h.category, "s": h.start, "e": h.end, "disc": h.discussion} for h in d.hits[:6]],
                    "reason": d.reason,
                    "notes": d.notes,
                    "source": "document" if n == "indirect" else "user",
                }
            )
    order = rs.permutation(len(items))
    items = [items[i] for i in order]
    for i, it in enumerate(items):
        it["i"] = i
    return {"description": "Seeded sample of held-out evaluation items with the decisions this repo's Sentinel made on them (recorded run).", "thresholds": th.to_dict(), "items": items}


def print_summary(results: dict) -> None:
    for sysname, per in results.items():
        print(f"\n[{sysname}]")
        for n, e in per.items():
            print(f"  {n:13s} n={e['n']:5d} P={e['precision']:.3f} R={e['recall']:.3f} F1={e['f1']:.3f} FPR={e['fpr']:.3f}" if e["n_pos"] and e["n_neg"] else f"  {n:13s} n={e['n']:5d} recall={e['recall']:.3f} fpr={e['fpr']:.3f}")


if __name__ == "__main__":
    main()
