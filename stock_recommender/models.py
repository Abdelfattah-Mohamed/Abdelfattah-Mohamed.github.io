"""Data models for the daily stock recommender."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(frozen=True)
class MarketQuote:
    """Normalized market quote fields used by the scoring engine."""

    ticker: str
    name: str
    price: float
    price_change_pct: float
    volume: int
    average_volume: int
    market_cap: int | None = None


@dataclass(frozen=True)
class TextSignal:
    """Mention and sentiment summary for a ticker from a text source."""

    ticker: str
    mentions: int = 0
    sentiment: float = 0.0
    sample_titles: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class StockScore:
    """Final score and explanation for a ranked stock candidate."""

    ticker: str
    name: str
    price: float
    score: float
    reasons: tuple[str, ...]
    risks: tuple[str, ...]
    market_quote: MarketQuote
    reddit_signal: TextSignal
    news_signal: TextSignal


@dataclass(frozen=True)
class RecommendationReport:
    """A complete daily run of ranked stock ideas."""

    generated_at: datetime
    recommendations: tuple[StockScore, ...]
    considered_count: int
    disclaimer: str = (
        "This is an automated research screen, not personalized financial "
        "advice. Review fundamentals, risk, position sizing, and your own "
        "financial situation before investing."
    )

    @classmethod
    def now(cls, recommendations: tuple[StockScore, ...], considered_count: int) -> "RecommendationReport":
        return cls(
            generated_at=datetime.now(timezone.utc),
            recommendations=recommendations,
            considered_count=considered_count,
        )
