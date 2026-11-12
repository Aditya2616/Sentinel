"""The Sentinel pipeline: normalise -> rules -> classifier -> decision (-> audit)."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Protocol

from .audit import AuditLog
from .decision import Thresholds, decide
from .normalize import normalize
from .rules import RuleHit, scan

MAX_CHARS = 200_000


class Scorer(Protocol):
    name: str

    def score(self, texts: list[str], windowed: bool = True): ...


@dataclass
class Decision:
    action: str  # allow | flag | block
    score: float | None  # calibrated classifier probability, None in rules-only mode
    reason: str
    hits: list[RuleHit] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    mode: str = "rules+classifier"
    source: str = "user"
    latency_ms: dict[str, float] = field(default_factory=dict)
    thresholds: dict = field(default_factory=dict)
    audit_id: str | None = None
    truncated: bool = False

    def to_dict(self) -> dict:
        d = asdict(self)
        d["rules_only"] = self.mode == "rules-only"
        return d


def classifier_texts(norm) -> list[str]:
    """What the classifier reads: the cleaned text, plus any decoded or de-obfuscated rendering that was found."""
    extra = [v.text for v in norm.views[1:] if v.name in ("base64", "hex", "tags", "leet", "spaced")]
    return [norm.base.text, *extra[:4]]


class Sentinel:
    def __init__(self, classifier: Scorer | None = None, thresholds: Thresholds | None = None, audit: AuditLog | None = None):
        self.classifier = classifier
        self.thresholds = thresholds or Thresholds()
        self.audit = audit

    @classmethod
    def load(cls, model_dir: Path | str | None = None, audit: AuditLog | None = None, require_model: bool = False, preset: str | None = None) -> Sentinel:
        """Load the trained classifier if present; otherwise run in rules-only mode."""
        from .classifier import DEFAULT_MODEL_DIR, TransformerClassifier, model_available

        d = Path(model_dir) if model_dir else DEFAULT_MODEL_DIR
        if model_available(d):
            return cls(TransformerClassifier(d), Thresholds.load(d / "thresholds.json", preset), audit)
        if require_model:
            raise FileNotFoundError(f"no trained model at {d}; run `sentinel train`")
        return cls(None, Thresholds(), audit)

    @property
    def mode(self) -> str:
        return "rules+classifier" if self.classifier is not None else "rules-only"

    def screen(self, text: str, source: str = "user", via: str = "screen", log: bool = True, extra: dict | None = None) -> Decision:
        t0 = time.perf_counter()
        truncated = len(text) > MAX_CHARS
        body = text[:MAX_CHARS]
        norm = normalize(body)
        res = scan(body, source, norm=norm)
        t1 = time.perf_counter()
        score = None
        if self.classifier is not None:
            score = float(self.classifier.score(classifier_texts(norm)).max())
        t2 = time.perf_counter()
        action, reason = decide(res.hits, score, self.thresholds, source)
        d = Decision(
            action=action,
            score=score,
            reason=reason,
            hits=res.hits,
            notes=norm.notes,
            mode=self.mode,
            source=source,
            latency_ms={"rules": round((t1 - t0) * 1000, 2), "classifier": round((t2 - t1) * 1000, 2), "total": round((t2 - t0) * 1000, 2)},
            thresholds=self.thresholds.to_dict(),
            truncated=truncated,
        )
        if self.audit and log:
            entry = self.audit.record(
                text=text,
                source=source,
                action=action,
                score=score,
                rule_ids=sorted({h.rule_id for h in res.hits}),
                categories=sorted({h.category for h in res.hits}),
                reason=reason,
                mode=self.mode,
                latency_ms=d.latency_ms["total"],
                via=via,
                extra=extra,
            )
            d.audit_id = entry["id"]
        return d

    def screen_batch(self, texts: list[str], source: str = "user") -> list[Decision]:
        """Screen many texts with one batched classifier call (used by evaluation). Not audited."""
        norms = [normalize(x[:MAX_CHARS]) for x in texts]
        results = [scan(x[:MAX_CHARS], source, norm=n) for x, n in zip(texts, norms, strict=True)]
        scores: list[float | None] = [None] * len(texts)
        if self.classifier is not None:
            flat, owner = [], []
            for i, n in enumerate(norms):
                for ct in classifier_texts(n):
                    flat.append(ct)
                    owner.append(i)
            raw = self.classifier.score(flat)
            best = [0.0] * len(texts)
            for o, s in zip(owner, raw, strict=True):
                best[o] = max(best[o], float(s))
            scores = best
        out = []
        for n, r, s in zip(norms, results, scores, strict=True):
            action, reason = decide(r.hits, s, self.thresholds, source)
            out.append(Decision(action=action, score=s, reason=reason, hits=r.hits, notes=n.notes, mode=self.mode, source=source, thresholds=self.thresholds.to_dict()))
        return out
