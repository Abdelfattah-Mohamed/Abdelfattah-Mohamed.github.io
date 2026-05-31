"""Small deterministic sentiment helper for headlines and social posts.

The project intentionally avoids a heavy machine-learning dependency so the
daily job can run anywhere Python is available. The scoring is transparent and
easy to tune as real recommendation results are reviewed.
"""

from __future__ import annotations

import re

POSITIVE_WORDS = {
    "accelerate",
    "beat",
    "beats",
    "bull",
    "bullish",
    "buy",
    "upgrade",
    "upgraded",
    "growth",
    "gain",
    "gains",
    "outperform",
    "profit",
    "profitable",
    "record",
    "rebound",
    "recover",
    "rally",
    "strong",
    "surge",
    "surges",
    "upside",
    "winner",
    "wins",
}

NEGATIVE_WORDS = {
    "bear",
    "bearish",
    "bankruptcy",
    "cut",
    "cuts",
    "downgrade",
    "downgraded",
    "drop",
    "drops",
    "fall",
    "falls",
    "fraud",
    "lawsuit",
    "loss",
    "miss",
    "misses",
    "plunge",
    "risk",
    "sell",
    "slump",
    "weak",
    "warning",
}

TOKEN_PATTERN = re.compile(r"[a-zA-Z][a-zA-Z'-]+")


def score_text(text: str) -> float:
    """Return a simple sentiment score between -1.0 and 1.0."""

    tokens = [token.lower() for token in TOKEN_PATTERN.findall(text)]
    if not tokens:
        return 0.0

    positive = sum(1 for token in tokens if token in POSITIVE_WORDS)
    negative = sum(1 for token in tokens if token in NEGATIVE_WORDS)
    total_hits = positive + negative
    if total_hits == 0:
        return 0.0

    return max(-1.0, min(1.0, (positive - negative) / total_hits))


def average_sentiment(texts: list[str]) -> float:
    """Average non-empty text sentiment scores."""

    scores = [score_text(text) for text in texts if text.strip()]
    if not scores:
        return 0.0
    return sum(scores) / len(scores)
