"""The README and model card must agree with docs/data (generated tables and every number quoted in prose),
and the results files must be internally consistent. Run `python scripts/render_docs.py` to fix a mismatch."""

from __future__ import annotations

import ast
import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

from sentinel.metrics import wilson

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "docs" / "data"


def _load_renderer():
    spec = importlib.util.spec_from_file_location("render_docs", ROOT / "scripts" / "render_docs.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["render_docs"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def eval_json():
    return json.loads((DATA / "eval.json").read_text(encoding="utf-8"))


def test_documents_match_results_files():
    assert _load_renderer().check() == []


def test_every_quoted_value_marker_is_known():
    r = _load_renderer()
    known = set(r.values())
    for doc in r.DOCS:
        used = set(re.findall(r"<!--v:(\w+)-->", doc.read_text(encoding="utf-8")))
        assert used <= known, f"{doc.name}: unknown keys {used - known}"


def test_counts_add_up_and_rates_match_counts(eval_json):
    for system, per in eval_json["results"].items():
        for name, e in per.items():
            c = e["confusion"]
            assert c["tp"] + c["fn"] == e["n_pos"], (system, name)
            assert c["fp"] + c["tn"] == e["n_neg"], (system, name)
            assert e["n_pos"] + e["n_neg"] == e["n"], (system, name)
            if e["n_pos"]:
                assert e["recall"] == pytest.approx(c["tp"] / e["n_pos"]), (system, name)
                assert tuple(e["recall_ci"]) == pytest.approx(wilson(c["tp"], e["n_pos"])), (system, name)
            if e["n_neg"]:
                assert e["fpr"] == pytest.approx(c["fp"] / e["n_neg"]), (system, name)
                assert tuple(e["fpr_ci"]) == pytest.approx(wilson(c["fp"], e["n_neg"])), (system, name)


def test_set_sizes_agree_across_systems_and_with_data_files(eval_json):
    sizes = {n: e["n"] for n, e in eval_json["results"]["sentinel"].items()}
    for system, per in eval_json["results"].items():
        assert {n: e["n"] for n, e in per.items()} == sizes, system
    build = eval_json["meta"]["build_report"]["sizes"]
    for n, k in sizes.items():
        assert build[f"test_{n}"]["n"] == k
    hand = ROOT / "data" / "hand_written"
    for name, key in (("hard_benign_v2_test.jsonl", "hard_benign_v2"), ("attacks_v2_test.jsonl", "attacks_v2")):
        assert sum(1 for line in (hand / name).read_text(encoding="utf-8").split("\n") if line.strip()) == sizes[key]


def test_preset_and_operating_tables_agree_with_results(eval_json):
    default = eval_json["meta"]["default_preset"]
    sets = eval_json["preset_results"][default]["sets"]
    for n, e in eval_json["results"]["sentinel"].items():
        if e["n_pos"]:
            assert sets[n]["recall_block"] == pytest.approx(e["recall"]), n
        if e["n_neg"]:
            assert sets[n]["fpr_block"] == pytest.approx(e["fpr"]), n
    op = eval_json["operating_table"]["systems"]["classifier"]
    for cell in op.values():
        for r in cell["recall"].values():
            assert r["k"] <= r["n"] and r["v"] == pytest.approx(r["k"] / r["n"])


def test_latency_states_load_and_device(eval_json):
    lat = eval_json["latency"]
    assert lat["device"] == "cpu" and lat["load"] and lat["threads"]
    assert "gpu" not in lat or lat["gpu"]["device"]


def test_readme_commands_exist():
    """Every `sentinel ...` and `python scripts/...` command in the README code blocks refers to a real subcommand, flag or file."""
    cli = (ROOT / "src" / "sentinel" / "cli.py").read_text(encoding="utf-8")
    subcommands = set(re.findall(r'add_parser\("([\w-]+)"', cli))
    flags = {
        "train": set(re.findall(r'add_argument\("(--[\w-]+)"', (ROOT / "src" / "sentinel" / "train.py").read_text(encoding="utf-8"))),
        "eval": set(re.findall(r'add_argument\("(--[\w-]+)"', (ROOT / "src" / "sentinel" / "evaluate.py").read_text(encoding="utf-8"))),
    }
    text = "".join((ROOT / n).read_text(encoding="utf-8") for n in ("README.md", "docs/RESULTS.md", "MODEL_CARD.md"))
    for line in re.findall(r"`(sentinel [^`]+)`|^(sentinel [^#\n]+)", text, flags=re.M):
        cmd = (line[0] or line[1]).strip()
        parts = cmd.split()
        if len(parts) < 2 or parts[1].startswith("-") or parts[1].startswith("<"):
            continue
        assert parts[1] in subcommands, cmd
        for tok in parts[2:]:
            if tok.startswith("--") and parts[1] in flags:
                assert tok in flags[parts[1]], cmd
    for script in set(re.findall(r"python (scripts/[\w./-]+\.py)", text)):
        assert (ROOT / script).exists(), script
        ast.parse((ROOT / script).read_text(encoding="utf-8"))
    for path in set(re.findall(r"\((docs/[\w./-]+)\)", text)):
        assert (ROOT / path).exists(), path
