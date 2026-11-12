"""Dataset download, cleaning, de-duplication and splitting.

Public datasets are downloaded at run time (never redistributed) at pinned revisions. Only my own hand-written
sets under data/hand_written are committed. `build()` writes data/processed/*.jsonl plus build_report.json.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
HAND = ROOT / "data" / "hand_written"

# repo id -> (pinned commit, licence as reported by the Hugging Face API on 2026-11-12, allow_patterns)
SOURCES: dict[str, dict] = {
    "neuralchemy/Prompt-injection-dataset": {"rev": "7d70432dfcf47a821612cbf9d34e9d9e3ad20e75", "license": "apache-2.0", "patterns": ["core/*", "README.md"]},
    "jackhhao/jailbreak-classification": {"rev": "2f2ceeb39658696fd3f462403562b6eea5306287", "license": "apache-2.0", "patterns": ["default/*", "README.md"]},
    "deepset/prompt-injections": {"rev": "4f61ecb038e9c3fb77e21034b22511b523772cdd", "license": "apache-2.0", "patterns": ["data/*", "README.md"]},
    "reshabhs/SPML_Chatbot_Prompt_Injection": {"rev": "02ce8084e979bc7d4c24ee35d22ecb7f2db96ff5", "license": "mit", "patterns": ["*.csv", "README.md"]},
    "databricks/databricks-dolly-15k": {"rev": "bdd27f4d94b9c1f951818a7da7fd7aeea5dbff1a", "license": "cc-by-sa-3.0", "patterns": ["*.jsonl", "README.md"]},
}


def local_dir(repo: str) -> Path:
    return RAW / repo.replace("/", "__")


def fetch() -> None:
    from huggingface_hub import snapshot_download

    for repo, meta in SOURCES.items():
        snapshot_download(repo, repo_type="dataset", revision=meta["rev"], allow_patterns=meta["patterns"], local_dir=local_dir(repo))
        print(f"fetched {repo} @ {meta['rev'][:8]} ({meta['license']})")


def norm_key(t: str) -> str:
    return re.sub(r"\s+", " ", t.lower()).strip()


_DE = set("der die das und ist nicht ich du ein eine zu von mit für auf wie was wer warum wann sie wir es den dem sind hat kann".split())
_EN = set("the and is not i you a an to of with for on how what who why when we it are has can this that".split())


def detect_lang(t: str) -> str:
    """Crude de/en/other detector: stop-word counts. Good enough to split deepset's EN/DE rows; not a language ID."""
    words = re.findall(r"[a-zäöüß]+", t.lower())
    de = sum(w in _DE for w in words)
    en = sum(w in _EN for w in words)
    if de > en:
        return "de"
    if en > 0 or not words:
        return "en"
    return "other"


def _read_jsonl(p: Path) -> list[dict]:
    # split on "\n" only: str.splitlines() would also break on U+2028 and other separators inside texts
    return [json.loads(line) for line in p.read_text(encoding="utf-8").split("\n") if line.strip()]


def _rows(df: pd.DataFrame, text: str, label: str | None, source: str, category: str | None = None, fixed_label: int | None = None) -> list[dict]:
    out = []
    for _, r in df.iterrows():
        out.append(
            {
                "text": str(r[text]),
                "label": int(r[label]) if fixed_label is None else fixed_label,
                "category": (str(r[category]) if category else source),
                "source": source,
            }
        )
    return out


def _load_all() -> dict[str, list[dict]]:
    """Load every source into named pools, before de-duplication."""
    pools: dict[str, list[dict]] = {}
    nc_dir = local_dir("neuralchemy/Prompt-injection-dataset") / "core"
    for split, name in (("train", "train"), ("validation", "val"), ("test", "test")):
        df = pd.read_parquet(next(nc_dir.glob(f"{split}-*.parquet")))
        # plain harmful requests (HarmBench) are a content-safety problem, not injection: drop the malicious ones
        df = df[~((df["source"] == "harmbench") & (df["label"] == 1))]
        pools[f"nc_{name}"] = _rows(df, "text", "label", "neuralchemy", "category")
    jb_dir = local_dir("jackhhao/jailbreak-classification") / "default"
    jtrain = pd.read_csv(jb_dir / "jailbreak_dataset_train.csv")
    jtest = pd.read_csv(jb_dir / "jailbreak_dataset_test.csv")
    for df in (jtrain, jtest):
        df["label"] = (df["type"] == "jailbreak").astype(int)
    rng = np.random.RandomState(7)
    idx = rng.permutation(len(jtrain))
    cut = int(len(idx) * 0.85)
    pools["jb_train"] = _rows(jtrain.iloc[idx[:cut]], "prompt", "label", "jackhhao", "type")
    pools["jb_val"] = _rows(jtrain.iloc[idx[cut:]], "prompt", "label", "jackhhao", "type")
    pools["jb_test"] = _rows(jtest, "prompt", "label", "jackhhao", "type")
    ds_dir = local_dir("deepset/prompt-injections") / "data"
    ds = pd.concat([pd.read_parquet(p) for p in sorted(ds_dir.glob("*.parquet"))], ignore_index=True)
    pools["deepset"] = [dict(r, lang=detect_lang(r["text"])) for r in _rows(ds, "text", "label", "deepset", None)]
    sp = pd.read_csv(local_dir("reshabhs/SPML_Chatbot_Prompt_Injection") / "spml_prompt_injection.csv")
    sp = sp.rename(columns={"User Prompt": "text", "Prompt injection": "label"})
    sp = sp[sp["text"].astype(str).str.len() <= 1500]
    pos = sp[sp["label"] == 1].sample(600, random_state=3)
    neg = sp[sp["label"] == 0].sample(600, random_state=3)
    pools["spml"] = _rows(pd.concat([pos, neg]), "text", "label", "spml", None)
    dl = pd.read_json(local_dir("databricks/databricks-dolly-15k") / "databricks-dolly-15k.jsonl", lines=True)
    dl = dl[(dl["instruction"].str.len() >= 8) & (dl["instruction"].str.len() <= 600)].sample(frac=1.0, random_state=11)
    ins = dl["instruction"].tolist()
    mk = lambda xs, tag: [{"text": t, "label": 0, "category": "dolly_benign", "source": tag} for t in xs]  # noqa: E731
    pools["dolly_train"] = mk(ins[:2500], "dolly")
    pools["dolly_val"] = mk(ins[2500:2900], "dolly")
    pools["dolly_test"] = mk(ins[2900:3900], "dolly")
    for split in ("train", "val", "test"):
        for kind in ("attacks", "hard_benign", "obfuscated"):
            pools[f"hw_{kind}_{split}"] = [dict(r, source="hand_written") for r in _read_jsonl(HAND / f"{kind}_{split}.jsonl")]
    pools["hw_indirect"] = [dict(r, source="hand_written_synthetic") for r in _read_jsonl(HAND / "indirect_test.jsonl")]
    return pools


def _near_dups(train_texts: list[str], texts: list[str], thr: float = 0.9) -> np.ndarray:
    """Boolean mask: which of `texts` have a char-n-gram TF-IDF cosine >= thr to any training text."""
    from sklearn.feature_extraction.text import TfidfVectorizer

    vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=2, sublinear_tf=True, max_features=300_000, dtype=np.float32)
    A = vec.fit_transform(train_texts)
    B = vec.transform(texts)
    mask = np.zeros(len(texts), dtype=bool)
    for i in range(0, B.shape[0], 500):
        sims = (B[i : i + 500] @ A.T).tocsr()
        mask[i : i + 500] = np.asarray(sims.max(axis=1).todense()).ravel() >= thr
    return mask


def build() -> dict:
    pools = _load_all()
    PROCESSED.mkdir(parents=True, exist_ok=True)
    report: dict = {"pools_raw": {k: len(v) for k, v in pools.items()}, "dropped": {}}

    def combine(names: list[str]) -> list[dict]:
        return [dict(r, pool=n) for n in names for r in pools[n]]

    train = combine(["nc_train", "jb_train", "dolly_train", "hw_attacks_train", "hw_hard_benign_train", "hw_obfuscated_train"])
    val = combine(["nc_val", "jb_val", "dolly_val", "hw_attacks_val", "hw_hard_benign_val", "hw_obfuscated_val"])
    tests = {
        "indist": combine(["nc_test", "jb_test"]),
        "deepset": combine(["deepset"]),
        "spml": combine(["spml"]),
        "hard_benign": combine(["hw_hard_benign_test"]),
        "attacks": combine(["hw_attacks_test"]),
        "obfuscated": combine(["hw_obfuscated_test"]),
        "dolly_benign": combine(["dolly_test"]),
        "indirect": combine(["hw_indirect"]),
    }

    def dedupe_within(rows: list[dict], name: str) -> list[dict]:
        seen, out = set(), []
        for r in rows:
            k = norm_key(r["text"])
            if k in seen:
                continue
            seen.add(k)
            out.append(r)
        report["dropped"][f"{name}_internal_exact"] = len(rows) - len(out)
        return out

    train = dedupe_within(train, "train")
    train_keys = {norm_key(r["text"]) for r in train}
    n0 = len(val)
    val = [r for r in dedupe_within(val, "val") if norm_key(r["text"]) not in train_keys]
    report["dropped"]["val_overlap_with_train"] = n0 - len(val) - report["dropped"]["val_internal_exact"]
    seen_eval = train_keys | {norm_key(r["text"]) for r in val}
    train_texts = [r["text"] for r in train]
    for name, rows in tests.items():
        rows = dedupe_within(rows, f"test_{name}")
        kept = [r for r in rows if norm_key(r["text"]) not in seen_eval]
        report["dropped"][f"test_{name}_exact_in_train_or_val"] = len(rows) - len(kept)
        if name not in ("indirect",):  # indirect docs are long and hand-made; the n-gram check is for external data
            mask = _near_dups(train_texts, [r["text"] for r in kept])
            report["dropped"][f"test_{name}_near_dup_in_train"] = int(mask.sum())
            kept = [r for r, m in zip(kept, mask, strict=True) if not m]
        tests[name] = kept
    sets = {"train": train, "val": val, **{f"test_{k}": v for k, v in tests.items()}}
    for name, rows in sets.items():
        with (PROCESSED / f"{name}.jsonl").open("w", encoding="utf-8", newline="\n") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    report["sizes"] = {k: {"n": len(v), "malicious": int(sum(r["label"] for r in v))} for k, v in sets.items()}
    report["sources"] = {k: {"revision": m["rev"], "license": m["license"]} for k, m in SOURCES.items()}
    (PROCESSED / "build_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def load(name: str) -> list[dict]:
    return _read_jsonl(PROCESSED / f"{name}.jsonl")


def available_sets() -> list[str]:
    return sorted(p.stem for p in PROCESSED.glob("*.jsonl"))
