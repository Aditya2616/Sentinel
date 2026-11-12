import numpy as np
import pytest

from sentinel.audit import AuditLog
from sentinel.decision import Thresholds
from sentinel.screen import Sentinel


class StubScorer:
    """Keyword stand-in for the transformer so service tests run offline and fast."""

    name = "stub"

    def __init__(self, table: dict[str, float] | None = None, default: float = 0.02):
        self.table = table or {}
        self.default = default

    def score(self, texts, windowed: bool = True):
        out = []
        for t in texts:
            p = self.default
            for k, v in self.table.items():
                if k in t.lower():
                    p = max(p, v)
            out.append(p)
        return np.array(out)


@pytest.fixture
def audit(tmp_path):
    return AuditLog(tmp_path / "audit.jsonl", text_chars=80)


@pytest.fixture
def sentinel(audit):
    scorer = StubScorer({"pwned": 0.97, "unrelated attack": 0.95, "suspicious": 0.6})
    return Sentinel(scorer, Thresholds(), audit)


@pytest.fixture
def rules_only(audit):
    return Sentinel(None, Thresholds(), audit)
