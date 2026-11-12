"""Zero-shot comparison against an existing public detector (never bundled, downloaded on demand).

ProtectAI deberta-v3-base-prompt-injection-v2 (Apache-2.0). It is used exactly as published: not fine-tuned,
not calibrated on this project's data.
"""

from __future__ import annotations

import numpy as np

REPO = "protectai/deberta-v3-base-prompt-injection-v2"


class ProtectAIDetector:
    name = REPO

    def __init__(self, threads: int | None = None, max_length: int = 512):
        import torch
        from huggingface_hub import snapshot_download
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        path = snapshot_download(REPO, allow_patterns=["*.json", "model.safetensors", "spm.model", "*.txt", "README.md"])
        if threads:
            torch.set_num_threads(threads)
        self.tok = AutoTokenizer.from_pretrained(path)
        self.model = AutoModelForSequenceClassification.from_pretrained(path).eval()
        self.max_length = max_length
        self._torch = torch

    def score(self, texts: list[str], windowed: bool = True, batch_size: int = 16) -> np.ndarray:
        torch = self._torch
        order = sorted(range(len(texts)), key=lambda i: len(texts[i]))
        out = np.zeros(len(texts))
        with torch.inference_mode():
            for b in range(0, len(order), batch_size):
                idx = order[b : b + batch_size]
                enc = self.tok([texts[i] for i in idx], truncation=True, max_length=self.max_length, padding=True, return_tensors="pt")
                p = torch.softmax(self.model(**enc).logits.float(), dim=-1)[:, 1].numpy()
                out[idx] = p
        return out
