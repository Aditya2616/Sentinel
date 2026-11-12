"""Transformer classifier inference: calibrated P(malicious) with sliding windows for long inputs."""

from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np

DEFAULT_MODEL_DIR = Path(os.environ.get("SENTINEL_MODEL_DIR", "models/sentinel"))


def pick_device(requested: str | None = None) -> str:
    """``cuda`` when available, else ``cpu``; override with the argument or SENTINEL_DEVICE."""
    import torch

    want = requested or os.environ.get("SENTINEL_DEVICE") or "auto"
    if want == "auto":
        return "cuda" if torch.cuda.is_available() else "cpu"
    return want


def model_available(model_dir: Path | str | None = None) -> bool:
    d = Path(model_dir) if model_dir else DEFAULT_MODEL_DIR
    return (d / "config.json").exists() and (d / "calibration.json").exists()


class TransformerClassifier:
    """Wraps a sequence-classification checkpoint trained by ``sentinel train``.

    Scores are P(malicious) after temperature scaling fitted on the validation split.
    Inputs longer than one window are scored window by window and the maximum is returned,
    so an instruction buried late in a long document still counts.
    """

    def __init__(self, model_dir: Path | str | None = None, max_length: int = 256, stride: int = 128, max_windows: int = 8, threads: int | None = None, device: str | None = None):
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        self.dir = Path(model_dir) if model_dir else DEFAULT_MODEL_DIR
        self.device = pick_device(device)
        if threads:
            torch.set_num_threads(threads)
        self.tok = AutoTokenizer.from_pretrained(self.dir)
        self.model = AutoModelForSequenceClassification.from_pretrained(self.dir, dtype=torch.float32).eval().to(self.device)
        cal = json.loads((self.dir / "calibration.json").read_text())
        self.temperature = float(cal.get("temperature", 1.0))
        self.name = cal.get("base_model", self.dir.name)
        self.max_length, self.stride, self.max_windows = max_length, stride, max_windows
        self._torch = torch

    def _wrap(self, ids: list[int]) -> list[int]:
        return [self.tok.cls_token_id, *ids, self.tok.sep_token_id]

    def _windows(self, text: str, windowed: bool) -> list[list[int]]:
        ids = self.tok(text, add_special_tokens=False, truncation=False)["input_ids"]
        body = self.max_length - 2
        if len(ids) <= body or not windowed:
            return [self._wrap(ids[:body])]
        starts = list(range(0, len(ids) - body + self.stride, self.stride))
        if starts[-1] + body < len(ids):
            starts.append(len(ids) - body)
        starts = sorted(set(min(s, len(ids) - body) for s in starts))
        if len(starts) > self.max_windows:  # keep the first windows and always the last
            starts = starts[: self.max_windows - 1] + [starts[-1]]
        return [self._wrap(ids[s : s + body]) for s in starts]

    def logits(self, texts: list[str], windowed: bool = True, batch_size: int = 32) -> np.ndarray:
        """Raw logit margin (malicious minus benign) per text, max over windows."""
        torch = self._torch
        seqs: list[list[int]] = []
        owner: list[int] = []
        for i, t in enumerate(texts):
            for w in self._windows(t, windowed):
                seqs.append(w)
                owner.append(i)
        margins = np.full(len(texts), -np.inf)
        order = sorted(range(len(seqs)), key=lambda k: len(seqs[k]))
        with torch.inference_mode():
            for b in range(0, len(order), batch_size):
                idx = order[b : b + batch_size]
                batch = self.tok.pad({"input_ids": [seqs[k] for k in idx]}, return_tensors="pt").to(self.device)
                out = self.model(**batch).logits.float()
                m = (out[:, 1] - out[:, 0]).cpu().numpy()
                for k, v in zip(idx, m, strict=True):
                    margins[owner[k]] = max(margins[owner[k]], v)
        return margins

    def score(self, texts: list[str], windowed: bool = True) -> np.ndarray:
        if not texts:
            return np.zeros(0)
        z = self.logits(texts, windowed) / self.temperature
        return 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))

    def score_one(self, text: str) -> float:
        return float(self.score([text])[0])
