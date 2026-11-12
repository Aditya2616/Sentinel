"""Metrics with honest uncertainty: Wilson intervals for rates, bootstrap for AUC."""

from __future__ import annotations

import math

import numpy as np


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (max(0.0, (c - h) / d), min(1.0, (c + h) / d))


def confusion(y, pred) -> dict[str, int]:
    y = np.asarray(y).astype(bool)
    pred = np.asarray(pred).astype(bool)
    return {"tp": int((y & pred).sum()), "fp": int((~y & pred).sum()), "tn": int((~y & ~pred).sum()), "fn": int((y & ~pred).sum())}


def prf(c: dict[str, int]) -> dict[str, float]:
    tp, fp, fn, tn = c["tp"], c["fp"], c["fn"], c["tn"]
    p = tp / (tp + fp) if tp + fp else float("nan")
    r = tp / (tp + fn) if tp + fn else float("nan")
    f1 = 2 * p * r / (p + r) if (tp + fp) and (tp + fn) and (p + r) > 0 else float("nan")
    fpr = fp / (fp + tn) if fp + tn else float("nan")
    return {"precision": p, "recall": r, "f1": f1, "fpr": fpr}


def _thin(d: dict[str, np.ndarray], max_points: int) -> dict[str, list[float]]:
    n = len(next(iter(d.values())))
    idx = np.arange(n) if n <= max_points else np.unique(np.linspace(0, n - 1, max_points).astype(int))
    return {k: [round(float(v[i]), 5) for i in idx] for k, v in d.items()}


def _cum(y, s):
    order = np.argsort(-s, kind="mergesort")
    ys, ss = y[order], s[order]
    tps, fps = np.cumsum(ys), np.cumsum(1 - ys)
    distinct = np.r_[np.where(np.diff(ss))[0], len(ss) - 1]
    return tps[distinct], fps[distinct], ss[distinct]


def roc_curve(y, s, max_points: int = 200) -> dict[str, list[float]]:
    y = np.asarray(y).astype(int)
    s = np.asarray(s, dtype=float)
    P, N = int(y.sum()), int((1 - y).sum())
    if P == 0 or N == 0:
        return {"fpr": [], "tpr": [], "thr": []}
    tps, fps, ss = _cum(y, s)
    return _thin({"fpr": np.r_[0, fps / N], "tpr": np.r_[0, tps / P], "thr": np.r_[1.0, ss]}, max_points)


def pr_curve(y, s, max_points: int = 200) -> dict[str, list[float]]:
    y = np.asarray(y).astype(int)
    s = np.asarray(s, dtype=float)
    P = int(y.sum())
    if P == 0:
        return {"recall": [], "precision": [], "thr": []}
    tps, fps, ss = _cum(y, s)
    return _thin({"recall": np.r_[0, tps / P], "precision": np.r_[1, tps / (tps + fps)], "thr": np.r_[1.0, ss]}, max_points)


def _rankdata(a: np.ndarray) -> np.ndarray:
    order = np.argsort(a, kind="mergesort")
    ranks = np.empty(len(a), dtype=float)
    sa = a[order]
    i = 0
    while i < len(a):
        j = i
        while j + 1 < len(a) and sa[j + 1] == sa[i]:
            j += 1
        ranks[order[i : j + 1]] = (i + j) / 2 + 1
        i = j + 1
    return ranks


def auc_roc(y, s) -> float:
    y = np.asarray(y).astype(int)
    s = np.asarray(s, dtype=float)
    P, N = int(y.sum()), int((1 - y).sum())
    if P == 0 or N == 0:
        return float("nan")
    ranks = _rankdata(s)
    return float((ranks[y == 1].sum() - P * (P + 1) / 2) / (P * N))


def average_precision(y, s) -> float:
    y = np.asarray(y).astype(int)
    P = int(y.sum())
    if P == 0:
        return float("nan")
    order = np.argsort(-np.asarray(s, dtype=float), kind="mergesort")
    ys = y[order]
    prec = np.cumsum(ys) / np.arange(1, len(ys) + 1)
    return float((prec * ys).sum() / P)


def bootstrap_ci(y, s, fn, reps: int = 300, seed: int = 0) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    y = np.asarray(y)
    s = np.asarray(s)
    vals = []
    for _ in range(reps):
        idx = rng.integers(0, len(y), len(y))
        v = fn(y[idx], s[idx])
        if not math.isnan(v):
            vals.append(v)
    if not vals:
        return (float("nan"), float("nan"))
    return (float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5)))


def threshold_at_fpr(y, s, target_fpr: float) -> float:
    """Lowest threshold whose FPR on the negatives is <= target_fpr (predict positive when score >= thr)."""
    y = np.asarray(y).astype(int)
    neg = np.sort(np.asarray(s, dtype=float)[y == 0])[::-1]
    if len(neg) == 0:
        return 0.5
    k = int(math.floor(target_fpr * len(neg)))
    if k >= len(neg):
        return 0.0
    return float(min(1.0, neg[k] + 1e-9))


def reliability(y, p, bins: int = 10) -> dict:
    y = np.asarray(y).astype(int)
    p = np.asarray(p, dtype=float)
    edges = np.linspace(0, 1, bins + 1)
    out = []
    for lo, hi in zip(edges[:-1], edges[1:], strict=True):
        m = (p >= lo) & ((p < hi) if hi < 1 else (p <= hi))
        if m.sum():
            out.append({"lo": float(lo), "hi": float(hi), "n": int(m.sum()), "mean_pred": float(p[m].mean()), "frac_pos": float(y[m].mean())})
    ece = sum(b["n"] * abs(b["mean_pred"] - b["frac_pos"]) for b in out) / max(1, len(y))
    return {"bins": out, "ece": float(ece)}


def summarize(y, s, thr: float, ci_reps: int = 300) -> dict:
    """Metric block for one (labels, scores) set at a decision threshold."""
    y = np.asarray(y).astype(int)
    s = np.asarray(s, dtype=float)
    c = confusion(y, s >= thr)
    n_neg, n_pos = c["fp"] + c["tn"], c["tp"] + c["fn"]
    out: dict = {"n": int(len(y)), "n_pos": int(n_pos), "n_neg": int(n_neg), "threshold": float(thr), "confusion": c, **prf(c)}
    if n_neg:
        out["fpr_ci"] = wilson(c["fp"], n_neg)
    if n_pos:
        out["recall_ci"] = wilson(c["tp"], n_pos)
    if n_pos and n_neg:
        out["roc_auc"] = auc_roc(y, s)
        out["pr_auc"] = average_precision(y, s)
        out["roc_auc_ci"] = bootstrap_ci(y, s, auc_roc, ci_reps)
    return out
