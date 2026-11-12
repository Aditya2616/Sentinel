"""Structured audit log: one JSON line per screening decision. Never stores keys; text storage is opt-in and capped."""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
import uuid
from pathlib import Path

_SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{16,}"),
    re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*\S{6,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"ghp_[A-Za-z0-9]{30,}"),
]


def redact(text: str) -> str:
    for p in _SECRET_PATTERNS:
        text = p.sub("[redacted]", text)
    return text


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()[:16]


class AuditLog:
    def __init__(self, path: Path | str | None = None, text_chars: int | None = None):
        self.path = Path(path or os.environ.get("SENTINEL_AUDIT_LOG", "logs/audit.jsonl"))
        self.text_chars = int(os.environ.get("SENTINEL_AUDIT_TEXT_CHARS", "200")) if text_chars is None else text_chars
        self._lock = threading.Lock()

    def record(self, *, text: str, source: str, action: str, score: float | None, rule_ids: list[str], categories: list[str], reason: str, mode: str, latency_ms: float, via: str = "screen", extra: dict | None = None) -> dict:
        entry = {
            "id": uuid.uuid4().hex[:12],
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + f".{int(time.time() * 1000) % 1000:03d}Z",
            "via": via,
            "source": source,
            "action": action,
            "score": None if score is None else round(float(score), 4),
            "rules": rule_ids,
            "categories": categories,
            "reason": reason,
            "mode": mode,
            "length": len(text),
            "sha256_16": text_hash(text),
            "latency_ms": round(latency_ms, 2),
        }
        if self.text_chars > 0:
            entry["preview"] = redact(text[: self.text_chars])
        if extra:
            entry.update(extra)
        line = json.dumps(entry, ensure_ascii=False)
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8", newline="\n") as f:
                f.write(line + "\n")
        return entry

    def read(self, limit: int = 100, action: str | None = None, rule: str | None = None) -> list[dict]:
        if not self.path.exists():
            return []
        rows = []
        for line in self.path.read_text(encoding="utf-8").split("\n"):
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if action and r.get("action") != action:
                continue
            if rule and rule not in r.get("rules", []):
                continue
            rows.append(r)
        return rows[-limit:][::-1]  # newest first
