"""Zero-shot comparison detector: ProtectAI's public prompt-injection classifier, used exactly as published.

Model: protectai/deberta-v3-base-prompt-injection-v2 (Apache-2.0 on its model card, pinned revision below). It is never
fine-tuned or calibrated on this project's data; only its decision threshold is chosen, on my validation split. It is a
comparison row, not part of Sentinel, and it is downloaded only by `sentinel eval --with-protectai` (about 0.7 GB).
"""

from __future__ import annotations

import numpy as np

REPO = "protectai/deberta-v3-base-prompt-injection-v2"
REVISION = "90c9989b1a342275dd0d1a95aad283c04e075671"
LICENSE = "apache-2.0"
PATTERNS = ["model.safetensors", "config.json", "tokenizer.json", "tokenizer_config.json", "special_tokens_map.json", "added_tokens.json", "spm.model", "README.md", "LICENSE"]


class ProtectAIDetector:
    """P(injection) from the published model: softmax over its two classes, label 1 = injection."""

    def __init__(self, device: str | None = None, threads: int = 2, max_length: int = 512):
        import torch
        from huggingface_hub import snapshot_download
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        from .classifier import pick_device

        path = snapshot_download(REPO, revision=REVISION, allow_patterns=PATTERNS)
        torch.set_num_threads(threads)
        self.device = pick_device(device)
        self.tok = AutoTokenizer.from_pretrained(path)
        self.model = AutoModelForSequenceClassification.from_pretrained(path, dtype=torch.float32).eval().to(self.device)
        self.max_length = max_length
        self._torch = torch

    def score(self, texts: list[str], batch_size: int = 32) -> np.ndarray:
        torch = self._torch
        order = sorted(range(len(texts)), key=lambda i: len(texts[i]))
        out = np.zeros(len(texts))
        with torch.inference_mode():
            for b in range(0, len(order), batch_size):
                idx = order[b : b + batch_size]
                enc = self.tok([texts[i] for i in idx], truncation=True, max_length=self.max_length, padding=True, return_tensors="pt").to(self.device)
                p = torch.softmax(self.model(**enc).logits.float(), dim=-1)[:, 1].cpu().numpy()
                out[idx] = p
        return out
