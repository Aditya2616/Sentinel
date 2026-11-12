"""Decision layer: rules + classifier score -> allow / flag / block with a human-readable reason."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

from .rules import SEVERITY_RANK, RuleHit

CATEGORY_LABEL = {
    "override": "instruction override",
    "spoof": "role or system spoofing",
    "leak": "prompt or secret extraction",
    "delimiter": "delimiter or markup smuggling",
    "obfuscation": "obfuscated content",
    "exfiltration": "data exfiltration",
    "jailbreak": "jailbreak",
    "indirect": "instructions hidden in retrieved content",
}


@dataclass
class Thresholds:
    """Operating points. Chosen on the validation split only (see `sentinel eval`), never on test sets."""

    t_flag: float = 0.50  # classifier score at which a prompt is flagged
    t_block: float = 0.90  # classifier score at which a prompt is blocked on its own
    t_agree: float = 0.30  # score at which a high-severity rule is allowed to block together with the classifier
    rule_block_high: bool = True  # a high-severity rule that is not in a quoted/"discussion" context blocks alone
    preset: str = "custom"  # strict | balanced | permissive when loaded from a thresholds file

    @staticmethod
    def load(path: Path | str | None, preset: str | None = None) -> Thresholds:
        """Read a thresholds file. A file with ``presets`` holds strict / balanced / permissive operating points;
        pick one with ``preset`` or the SENTINEL_PRESET environment variable (default: the file's own default)."""
        if path and Path(path).exists():
            d = json.loads(Path(path).read_text())
            if "presets" in d:
                name = preset or os.environ.get("SENTINEL_PRESET") or d.get("default", "balanced")
                if name not in d["presets"]:
                    raise ValueError(f"unknown preset {name!r}; choose one of {sorted(d['presets'])}")
                d = {**d["presets"][name], "preset": name}
            return Thresholds(**{k: d[k] for k in ("t_flag", "t_block", "t_agree", "rule_block_high", "preset") if k in d})
        return Thresholds()

    def to_dict(self) -> dict:
        return asdict(self)


def effective_severity(h: RuleHit) -> int:
    """Severity after context: a hit inside quotes or introduced as an example counts one level lower."""
    s = SEVERITY_RANK[h.severity]
    if h.discussion:
        s -= 1
    return s


def decide(hits: list[RuleHit], score: float | None, th: Thresholds, source: str = "user") -> tuple[str, str]:
    """Return (action, reason). ``score`` is None in rules-only mode."""
    eff = [(effective_severity(h), h) for h in hits]
    top_eff = max((e for e, _ in eff), default=0)
    top = max(eff, key=lambda x: (x[0], -x[1].start), default=(0, None))[1]
    high_standing = [h for e, h in eff if e >= 3]
    where = "retrieved content" if source != "user" else "prompt"

    def rule_phrase(h: RuleHit) -> str:
        label = CATEGORY_LABEL.get(h.category, h.category)
        snippet = f' ("{h.matched.strip()[:60]}")' if h.matched and h.rule_id[:3] not in ("OBF",) else ""
        extra = " after decoding" if h.obfuscated and h.view != "base" else ""
        return f"{h.rule_id} {label}{extra}{snippet}"

    if score is not None and score >= th.t_block:
        why = f"Blocked: the classifier scores this {where} {score:.2f} for injection (block threshold {th.t_block:.2f})"
        if top is not None:
            why += f"; rule {rule_phrase(top)} also matched"
        return "block", why + "."
    if high_standing:
        h = high_standing[0]
        if score is not None and score >= th.t_agree:
            return "block", f"Blocked: high-severity rule {rule_phrase(h)} matched and the classifier agrees ({score:.2f} >= {th.t_agree:.2f})."
        if th.rule_block_high:
            tail = f" (classifier {score:.2f})" if score is not None else " (rules-only mode, no classifier loaded)"
            return "block", f"Blocked: high-severity rule {rule_phrase(h)} matched{tail}."
    if score is not None and score >= th.t_flag:
        why = f"Flagged: the classifier scores this {where} {score:.2f} (flag threshold {th.t_flag:.2f})"
        if top is not None:
            why += f"; rule {rule_phrase(top)} also matched"
        return "flag", why + "."
    if top_eff >= 1 and top is not None:
        ctx = " It reads like a quoted or discussed example, so it was not blocked." if top.discussion else ""
        tail = f" (classifier {score:.2f})" if score is not None else ""
        return "flag", f"Flagged: rule {rule_phrase(top)} matched{tail}.{ctx}"
    if score is None:
        return "allow", "Allowed: no rule matched (rules-only mode, no classifier loaded)."
    return "allow", f"Allowed: no rule matched and the classifier score is {score:.2f}."
