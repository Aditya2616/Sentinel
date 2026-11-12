"""Rule engine: regex rules over normalised views, plus structural obfuscation signals."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from importlib import resources
from pathlib import Path

import yaml

from .normalize import Normalized, normalize

SEVERITY_RANK = {"low": 1, "medium": 2, "high": 3}
ALL_SOURCES = ("user", "document", "tool")

_QUOTE_OPEN = "\"'`“‘«„"
_QUOTE_CLOSE = "\"'`”’»“"
_META_WORDS = re.compile(
    r"(what does|what is|what are|meaning of|mean by|explain|example|examples|phrase|phrases|called|known as|"
    r"the term|detect|detection|classif|label|dataset|filter|defen[sc]e|defend|security|research|training data|"
    r"how do (attackers|hackers)|attackers|owasp|red.?team|translate|quote|quoted|sentence|string|"
    r"blog post|paper|lecture|teach|students|slide)",
    re.I,
)


@dataclass(frozen=True)
class Rule:
    id: str
    category: str
    severity: str
    description: str
    pattern: re.Pattern[str]
    applies_to: tuple[str, ...] = ALL_SOURCES
    positive: tuple[str, ...] = ()
    negative: tuple[str, ...] = ()

    def public(self) -> dict:
        return {
            "id": self.id,
            "category": self.category,
            "severity": self.severity,
            "description": self.description,
            "applies_to": list(self.applies_to),
        }


@dataclass
class RuleHit:
    rule_id: str
    category: str
    severity: str
    description: str
    start: int  # span on the ORIGINAL text
    end: int
    view: str = "base"
    matched: str = ""
    discussion: bool = False  # quoted or introduced as an example, so likely talking about an attack
    obfuscated: bool = False  # only found after undoing obfuscation

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RuleResult:
    hits: list[RuleHit] = field(default_factory=list)
    normalized: Normalized | None = None

    @property
    def max_severity(self) -> int:
        return max((SEVERITY_RANK[h.severity] for h in self.hits), default=0)


def _load_rules(path: Path | None = None) -> list[Rule]:
    if path is None:
        raw = resources.files("sentinel").joinpath("rules_data/rules.yaml").read_text(encoding="utf-8")
    else:
        raw = path.read_text(encoding="utf-8")
    rules: list[Rule] = []
    for r in yaml.safe_load(raw):
        rules.append(
            Rule(
                id=r["id"],
                category=r["category"],
                severity=r["severity"],
                description=r["description"].strip(),
                pattern=re.compile(r["pattern"], re.I | re.M),
                applies_to=tuple(r.get("applies_to", ALL_SOURCES)),
                positive=tuple(r.get("positive", ())),
                negative=tuple(r.get("negative", ())),
            )
        )
    ids = [r.id for r in rules]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate rule id")
    return rules


@lru_cache(maxsize=1)
def default_rules() -> tuple[Rule, ...]:
    return tuple(_load_rules())


def _discussion_context(text: str, start: int, end: int) -> bool:
    """True if the match is quoted or introduced as an example/subject rather than addressed to the model."""
    before = text[max(0, start - 3) : start]
    after = text[end : end + 3]
    if any(c in _QUOTE_OPEN for c in before) and any(c in _QUOTE_CLOSE for c in after):
        return True
    # inside a fenced or inline code span
    prefix = text[:start]
    if prefix.count("```") % 2 == 1 or prefix.count("`") % 2 == 1:
        return True
    return bool(_META_WORDS.search(text[max(0, start - 70) : start]))


def _structural_hits(norm: Normalized) -> list[RuleHit]:
    s = norm.stats
    n = len(norm.original)
    hits: list[RuleHit] = []
    if s.get("tags"):
        hits.append(RuleHit("OBF-002", "obfuscation", "high", "Hidden text in Unicode tag characters.", 0, n, "tags", obfuscated=True))
    if s.get("invisible", 0) >= 1:
        sev = "medium" if s["invisible"] >= 3 else "low"
        hits.append(RuleHit("OBF-001", "obfuscation", sev, "Invisible or bidirectional control characters in the text.", 0, n, "base", obfuscated=True))
    if s.get("homoglyph_tokens"):
        hits.append(RuleHit("OBF-003", "obfuscation", "medium", "Look-alike letters from another script mixed into words.", 0, n, "base", obfuscated=True))
    for v in norm.views:
        if v.name in ("base64", "hex"):
            start, end = v.original_span(0, len(v.text))
            hits.append(RuleHit("OBF-005", "obfuscation", "medium", f"An encoded ({v.name}) text payload is embedded in the input.", start, end, v.name, v.text[:80], obfuscated=True))
    return hits


def scan(text: str, source: str = "user", rules: tuple[Rule, ...] | None = None, norm: Normalized | None = None) -> RuleResult:
    """Run all rules that apply to ``source`` over every view of ``text``."""
    norm = norm or normalize(text)
    rules = rules if rules is not None else default_rules()
    hits: list[RuleHit] = []
    seen: set[tuple[str, int, int]] = set()
    for rule in rules:
        if source not in rule.applies_to:
            continue
        per_rule = 0
        for view in norm.views:
            for m in rule.pattern.finditer(view.text):
                a, b = view.original_span(m.start(), m.end())
                key = (rule.id, a, b)
                if key in seen:
                    continue
                seen.add(key)
                obf = view.name != "base"
                hits.append(
                    RuleHit(
                        rule_id=rule.id,
                        category=rule.category,
                        severity=rule.severity,
                        description=rule.description,
                        start=a,
                        end=b,
                        view=view.name,
                        matched=m.group()[:120],
                        discussion=(not obf) and _discussion_context(norm.original, a, b),
                        obfuscated=obf,
                    )
                )
                per_rule += 1
                if per_rule >= 3:
                    break
            if per_rule >= 3:
                break
    if source in ("user", "document", "tool"):
        hits.extend(_structural_hits(norm))
    hits.sort(key=lambda h: (-SEVERITY_RANK[h.severity], h.start))
    return RuleResult(hits=hits, normalized=norm)


def rule_catalogue() -> list[dict]:
    items = [r.public() for r in default_rules()]
    items += [
        {"id": "OBF-001", "category": "obfuscation", "severity": "low/medium", "description": "Invisible or bidirectional control characters.", "applies_to": list(ALL_SOURCES)},
        {"id": "OBF-002", "category": "obfuscation", "severity": "high", "description": "Hidden text in Unicode tag characters.", "applies_to": list(ALL_SOURCES)},
        {"id": "OBF-003", "category": "obfuscation", "severity": "medium", "description": "Look-alike letters from another script mixed into words.", "applies_to": list(ALL_SOURCES)},
        {"id": "OBF-005", "category": "obfuscation", "severity": "medium", "description": "Embedded base64 or hex text payload.", "applies_to": list(ALL_SOURCES)},
    ]
    return items
