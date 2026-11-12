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
from .sysinfo import load_note

ROOT = D.ROOT
OUT = ROOT / "docs" / "data"
SCORES = ROOT / "runs" / "scores"
TEST_SETS = ["indist", "deepset", "spml", "spml_dev", "hard_benign", "hard_benign_dedup", "hard_benign_v2", "attacks_v2", "obfuscated", "attacks", "dolly_benign", "indirect"]
SET_LABEL = {
    "indist": "In-distribution (neuralchemy + jackhhao test, de-duplicated)",
    "deepset": "OOD: deepset/prompt-injections (EN + DE)",
    "spml": "OOD-test: SPML chatbot prompts (half, fixed-seed split)",
    "spml_dev": "OOD-dev: other half of SPML (model selection only, never reported as a result)",
    "hard_benign": "Hard benign v1: talks about injection (hand-written; looked at once before the round-two re-selection)",
    "hard_benign_dedup": "Hard benign v1, templated near-duplicates removed",
    "hard_benign_v2": "Hard benign v2 (hand-written, frozen before the round-two models were run)",
    "attacks_v2": "Plain attacks v2 (hand-written, frozen before the round-two models were run)",
    "obfuscated": "Obfuscated attacks + obfuscated benign (hand-written)",
    "attacks": "Plain attacks (hand-written)",
    "dolly_benign": "Everyday benign (Dolly-15k held-out)",
    "indirect": "Indirect injection in documents (SYNTHETIC, small)",
}


SHORT_NAMES = {"sentence-transformers/all-MiniLM-L6-v2": "MiniLM-L6", "microsoft/deberta-v3-xsmall": "DeBERTa-v3-xsmall"}


def system_labels(default_model: str, alt_model: str | None) -> dict[str, str]:
    """One name per system, used identically in the README, model card, UI and eval.json."""
    short = lambda m: SHORT_NAMES.get(m, m.split("/")[-1])  # noqa: E731
    labels = {
        "sentinel": "Sentinel (rules + classifier + decision)",
        "classifier": f"{short(default_model)} classifier (default)",
        "rules_only": "Rules only",
        "tfidf": "TF-IDF + logistic regression",
    }
    if alt_model:
        labels["classifier_alt"] = f"{short(alt_model)} classifier"
    return labels


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


HARD_BENIGN_VAL_POOLS = ("hw_hard_benign_val", "hw_hn_val")
# Rule fixed before any round-two model was trained: for each preset, the block threshold is the lowest score threshold whose
# validation false-positive rate is at or below these caps on (hard-benign text, everyday benign text); the flag threshold
# uses looser caps. Validation only; no test set is consulted.
PRESET_CAPS = {
    "strict": {"block": (0.01, 0.005), "flag": (0.05, 0.02)},
    "balanced": {"block": (0.02, 0.005), "flag": (0.10, 0.02)},
    "permissive": {"block": (0.05, 0.01), "flag": (0.20, 0.03)},
}
DEFAULT_PRESET = "balanced"


def val_masks(val_rows: list[dict]) -> tuple[np.ndarray, np.ndarray]:
    hb = np.array([r.get("pool") in HARD_BENIGN_VAL_POOLS for r in val_rows])
    dolly = np.array([r.get("pool") == "dolly_val" for r in val_rows])
    return hb, dolly


def lowest_threshold(scores: np.ndarray, hb: np.ndarray, dolly: np.ndarray, caps: tuple[float, float]) -> float:
    """Lowest threshold whose FPR is within ``caps`` on the validation hard-benign set and the everyday-benign set."""
    t_hb = threshold_at_fpr(np.zeros(int(hb.sum())), scores[hb], caps[0])
    t_dl = threshold_at_fpr(np.zeros(int(dolly.sum())), scores[dolly], caps[1])
    return float(max(t_hb, t_dl))


def choose_presets(val_y: np.ndarray, val_s: np.ndarray, val_rows: list[dict], val_decide_fn) -> tuple[dict[str, Thresholds], dict]:
    """strict / balanced / permissive operating points from the validation split only."""
    hb, dolly = val_masks(val_rows)
    t_agree0 = threshold_at_fpr(val_y, val_s, 0.10)
    out: dict[str, Thresholds] = {}
    info: dict = {"hard_benign_val_n": int(hb.sum()), "everyday_val_n": int(dolly.sum()), "caps": PRESET_CAPS}
    for name, caps in PRESET_CAPS.items():
        t_block = lowest_threshold(val_s, hb, dolly, caps["block"])
        t_flag = min(t_block, lowest_threshold(val_s, hb, dolly, caps["flag"]))
        t_agree = min(t_flag, t_agree0)
        chosen, rec = None, {}
        for rbh in (True, False):  # may a high-severity rule block on its own? keep it unless that breaks the hard-benign cap
            th = Thresholds(t_flag=t_flag, t_block=t_block, t_agree=t_agree, rule_block_high=rbh, preset=name)
            blocked = np.array([a == "block" for a in val_decide_fn(th)])
            rec[f"rule_block_high={rbh}"] = {"hard_benign_val_fpr": float(blocked[hb].mean()), "everyday_val_fpr": float(blocked[dolly].mean())}
            if chosen is None and blocked[hb].mean() <= caps["block"][0] + 1e-9:
                chosen = th
        out[name] = chosen or Thresholds(t_flag=t_flag, t_block=t_block, t_agree=t_agree, rule_block_high=False, preset=name)
        info[name] = rec
    return out, info


def operating_table(systems: dict, val_scores: dict, val_rows: list[dict], Y: dict, T_sets: list[str], levels=(0.01, 0.02, 0.05)) -> dict:
    """Per model: thresholds that give 1, 2 and 5% FPR on the validation hard-benign set, and what they do on every test set."""
    from .metrics import wilson

    hb, _ = val_masks(val_rows)
    out: dict = {"levels": list(levels), "systems": {}}
    for sname, per in systems.items():
        out["systems"][sname] = {}
        for lv in levels:
            thr = float(threshold_at_fpr(np.zeros(int(hb.sum())), val_scores[sname][hb], lv))
            rec, fpr = {}, {}
            for n in T_sets:
                y, sc = Y[n], per[n]
                if y.sum():
                    k = int(((sc >= thr) & (y == 1)).sum())
                    rec[n] = {"v": k / int(y.sum()), "ci": wilson(k, int(y.sum())), "k": k, "n": int(y.sum())}
                if (1 - y).sum():
                    k = int(((sc >= thr) & (y == 0)).sum())
                    fpr[n] = {"v": k / int((1 - y).sum()), "ci": wilson(k, int((1 - y).sum())), "k": k, "n": int((1 - y).sum())}
            out["systems"][sname][str(lv)] = {"threshold": thr, "recall": rec, "fpr": fpr}
    return out


def _clean(o):
    """Make the result JSON-safe: NaN/inf become null (browsers reject NaN), numpy scalars become Python numbers."""
    import math

    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, np.generic):
        o = o.item()
    if isinstance(o, float) and not math.isfinite(o):
        return None
    return o


def _latency(fn, items: list[str], reps: int = 1) -> dict:
    ts = []
    for t in items:
        t0 = time.perf_counter()
        for _ in range(reps):
            fn(t)
        ts.append((time.perf_counter() - t0) / reps * 1000)
    a = np.array(ts)
    return {"n": len(a), "p50_ms": float(np.percentile(a, 50)), "p95_ms": float(np.percentile(a, 95)), "mean_ms": float(a.mean())}


def measure_latency(model_dir: Path, th: Thresholds, base: TfidfBaseline, tests: dict, n_items: int, cpu_threads: int, device: str | None) -> dict:
    """Per-prompt latency. CPU figures come from a dedicated CPU copy of the model (never the GPU one), with the
    machine's load recorded beside them; the GPU figure, when a GPU is available, is reported separately."""
    import torch

    from .classifier import TransformerClassifier, pick_device

    pool = [r["text"] for n in ("dolly_benign", "hard_benign", "attacks", "indist", "deepset") for r in tests[n]]
    rs = np.random.RandomState(5)
    items = [pool[i] for i in rs.choice(len(pool), min(n_items, len(pool)), replace=False)]
    load = load_note()  # measured before the model is loaded, so it reflects the machine and not this process
    clf_cpu = TransformerClassifier(model_dir, threads=cpu_threads, device="cpu")
    torch.set_num_threads(cpu_threads)
    sent_cpu = Sentinel(clf_cpu, th)
    for t in items[:5]:
        sent_cpu.screen(t, log=False)
    latency = {
        "rules_only": _latency(lambda t: scan(t), items),
        "classifier_single": _latency(lambda t: clf_cpu.score([t]), items),
        "sentinel_full": _latency(lambda t: sent_cpu.screen(t, log=False), items),
        "tfidf": _latency(lambda t: base.score([t]), items),
        "threads": cpu_threads,
        "cpu": platform.processor(),
        "device": "cpu",
        "load": load,
        "measured": time.strftime("%Y-%m-%d %H:%M"),
        "note": f"CPU figures: {cpu_threads} torch threads, float32, {load}. Busy machines inflate them: treat as an upper-bound ballpark unless the load is low.",
    }
    t0 = time.perf_counter()
    clf_cpu.score(items[:64])
    latency["classifier_batch64_ms_per_prompt"] = (time.perf_counter() - t0) / 64 * 1000
    dev = pick_device(device)
    if dev != "cpu":
        clf = TransformerClassifier(model_dir, threads=2, device=dev)
        sent = Sentinel(clf, th)
        sent.screen(items[0], log=False)
        latency["gpu"] = {"device": dev, "classifier_single": _latency(lambda t: clf.score([t]), items), "sentinel_full": _latency(lambda t: sent.screen(t, log=False), items)}
        t0 = time.perf_counter()
        clf.score(items[:64])
        latency["gpu"]["classifier_batch64_ms_per_prompt"] = (time.perf_counter() - t0) / 64 * 1000
    return latency


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Evaluate Sentinel and baselines")
    ap.add_argument("--model-dir", default="models/sentinel")
    ap.add_argument("--train-set", default="train", help="training file used to fit the TF-IDF baseline (match the classifier's)")
    ap.add_argument("--also", default=None, help="a second trained classifier directory, reported as its own row next to the main one")
    ap.add_argument("--device", default=None, help="cuda | cpu | auto for scoring (latency is always measured on the CPU as well)")
    ap.add_argument("--out", default=str(OUT), help="output directory for eval.json, stream.json, rules.json")
    ap.add_argument("--latency-only", action="store_true", help="re-measure latency only and patch it into the existing eval.json (run on a quiet machine)")
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--threads", type=int, default=2)
    ap.add_argument("--latency-threads", type=int, default=3, help="CPU threads for the dedicated CPU latency measurement")
    ap.add_argument("--latency-n", type=int, default=150)
    a = ap.parse_args(argv)

    import torch

    torch.set_num_threads(a.threads)
    from .classifier import TransformerClassifier

    model_dir = Path(a.model_dir)
    if a.latency_only:
        ej = Path(a.out) / "eval.json"
        rec = json.loads(ej.read_text(encoding="utf-8"))
        base_ = TfidfBaseline().fit([r["text"] for r in D.load(a.train_set)], [r["label"] for r in D.load(a.train_set)])
        rec["latency"] = _clean(measure_latency(model_dir, Thresholds(**rec["meta"]["thresholds"]), base_, {n: D.load(f"test_{n}") for n in TEST_SETS}, a.latency_n, a.latency_threads, a.device))
        ej.write_text(json.dumps(rec, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(json.dumps(rec["latency"]["note"]), flush=True)
        return
    clf = TransformerClassifier(model_dir, threads=a.threads, device=a.device)
    scoring_device = f"{clf.device} (float32)"
    print(f"scoring device: {scoring_device}", flush=True)
    val = D.load("val")
    train = D.load(a.train_set)
    tests = {n: D.load(f"test_{n}") for n in TEST_SETS}
    Y = {n: np.array([r["label"] for r in rows]) for n, rows in tests.items()}
    T = {n: [r["text"] for r in rows] for n, rows in tests.items()}
    val_y, val_t = np.array([r["label"] for r in val]), [r["text"] for r in val]
    refresh = a.refresh

    systems: dict[str, dict[str, np.ndarray]] = {}  # system -> set -> score
    val_scores: dict[str, np.ndarray] = {}

    # --- fine-tuned classifier (calibrated probability)
    print("scoring classifier", flush=True)
    val_scores["classifier"] = _cached(f"{model_dir.name}__val", lambda: clf.score(val_t), refresh, len(val_t))
    systems["classifier"] = {n: _cached(f"{model_dir.name}__{n}", lambda n=n: clf.score(T[n]), refresh, len(T[n])) for n in TEST_SETS}

    # --- optional second classifier (reported raw, threshold at 1% validation FPR like the baseline)
    alt_name, alt_log = None, None
    if a.also:
        alt = TransformerClassifier(Path(a.also), threads=a.threads, device=a.device)
        key = "clf_" + Path(a.also).name
        val_scores["alt"] = _cached(f"{key}__val", lambda: alt.score(val_t), refresh, len(val_t))
        systems["alt"] = {n: _cached(f"{key}__{n}", lambda n=n: alt.score(T[n]), refresh, len(T[n])) for n in TEST_SETS}
        alt_name = alt.name
        alt_log = json.loads((Path(a.also) / "training_log.json").read_text()) if (Path(a.also) / "training_log.json").exists() else None
        del alt

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

    presets, policy_info = choose_presets(val_y, val_scores["classifier"], val, val_decide)
    th = presets[DEFAULT_PRESET]
    sent.thresholds = th
    hb_val, dolly_val = val_masks(val)
    (model_dir / "thresholds.json").write_text(
        json.dumps({"default": DEFAULT_PRESET, "presets": {k: {x: v for x, v in t.to_dict().items() if x != "preset"} for k, t in presets.items()}, "selection": policy_info}, indent=2)
    )
    print("thresholds", {k: (round(t.t_flag, 3), round(t.t_block, 3), t.rule_block_high) for k, t in presets.items()}, flush=True)
    sys_thr = {s: lowest_threshold(val_scores[s], hb_val, dolly_val, PRESET_CAPS[DEFAULT_PRESET]["block"]) for s in val_scores}

    # --- full Sentinel pipeline decisions
    print("running full pipeline", flush=True)
    decisions = {n: sent.screen_batch(T[n], _src(n)) for n in TEST_SETS}
    preset_decisions = {DEFAULT_PRESET: decisions}
    for pname, pth in presets.items():
        if pname != DEFAULT_PRESET:
            sent.thresholds = pth
            preset_decisions[pname] = {n: sent.screen_batch(T[n], _src(n)) for n in TEST_SETS}
    sent.thresholds = th
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
        if score is not None and entry["n_pos"] and entry["n_neg"]:
            # operating curve read-out: recall when the threshold is set to hit a given FPR on this set's own benign side
            entry["recall_at_fpr"] = {str(f): float(((score >= threshold_at_fpr(y, score, f)) & (y == 1)).sum() / y.sum()) for f in (0.01, 0.05)}
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
        if "alt" in systems:
            put("classifier_alt", n, systems["alt"][n] >= sys_thr["alt"], systems["alt"][n], sys_thr["alt"])
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
    for n in [x for x in TEST_SETS if x not in ("spml_dev", "hard_benign_dedup")]:
        for r, d in zip(tests[n], decisions[n], strict=True):
            row = {"set": n, "text": r["text"][:220], "score": d.score, "action": d.action, "rules": sorted({h.rule_id for h in d.hits}), "category": r.get("category")}
            if r["label"] == 0 and d.action == "block":
                errors["false_positives"].append(row)
            if r["label"] == 1 and d.action == "allow":
                errors["false_negatives"].append(row)
    errors["false_positives"] = errors["false_positives"][:60]
    errors["false_negatives"] = errors["false_negatives"][:60]

    # --- latency: CPU (dedicated CPU copy of the model) plus a separately labelled GPU figure
    print("measuring latency", flush=True)
    latency = measure_latency(model_dir, th, base, tests, a.latency_n, a.latency_threads, a.device)

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
        "scoring_device": scoring_device,
        "alt_model": alt_name,
        "system_labels": system_labels(clf.name, alt_name),
        "presets": {k: t.to_dict() for k, t in presets.items()},
        "default_preset": DEFAULT_PRESET,
        "preset_rule": "block threshold = lowest threshold with validation hard-benign FPR and everyday-benign FPR within the preset caps (see PRESET_CAPS); flag threshold uses looser caps",
        "val_hard_benign_n": int(hb_val.sum()),
        "distinct_hard_benign": json.loads((D.PROCESSED / "build_report.json").read_text()).get("distinct_hard_benign"),
        "alt_training_log": alt_log,
        "training_log": json.loads((model_dir / "training_log.json").read_text()) if (model_dir / "training_log.json").exists() else None,
        "sources": D.SOURCES,
        "build_report": json.loads((D.PROCESSED / "build_report.json").read_text()),
        "set_labels": SET_LABEL,
        "pooled": pooled_conf,
    }
    from .metrics import wilson

    preset_results: dict = {}
    for pname, dec in preset_decisions.items():
        preset_results[pname] = {"thresholds": presets[pname].to_dict(), "sets": {}}
        for n in TEST_SETS:
            blk = np.array([d.action == "block" for d in dec[n]])
            alr = np.array([d.action != "allow" for d in dec[n]])
            y = Y[n]
            e: dict = {"n_pos": int(y.sum()), "n_neg": int((1 - y).sum())}
            if e["n_pos"]:
                e["recall_block"] = float(blk[y == 1].mean())
                e["recall_flag_or_block"] = float(alr[y == 1].mean())
                e["recall_ci"] = wilson(int(blk[y == 1].sum()), e["n_pos"])
            if e["n_neg"]:
                e["fpr_block"] = float(blk[y == 0].mean())
                e["fpr_ci"] = wilson(int(blk[y == 0].sum()), e["n_neg"])
                e["fp"] = int(blk[y == 0].sum())
            preset_results[pname]["sets"][n] = e
    op_systems = {k: systems[k] for k in ("classifier", "alt", "tfidf") if k in systems}
    op_names = {"classifier": "classifier", "alt": "classifier_alt", "tfidf": "tfidf"}
    op = operating_table(op_systems, val_scores, val, Y, TEST_SETS)
    op["systems"] = {op_names[k]: v for k, v in op["systems"].items()}
    out = {"meta": meta, "preset_results": preset_results, "operating_table": op, "results": results, "curves": curves, "deepset_by_language": by_lang, "per_category_recall_indist": cats, "calibration": cal, "shortcuts": shortcuts, "errors": errors, "latency": latency, "slider": slider}
    out_dir = Path(a.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "eval.json").write_text(json.dumps(_clean(out), ensure_ascii=False, separators=(",", ":"), default=float), encoding="utf-8")
    (out_dir / "stream.json").write_text(json.dumps(_clean(stream), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (out_dir / "rules.json").write_text(json.dumps(rule_catalogue(), indent=1), encoding="utf-8")
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
