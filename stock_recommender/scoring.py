"""Ranking logic for daily stock ideas."""

from __future__ import annotations

import math

from stock_recommender.models import MarketQuote, StockScore, TextSignal


MIN_PRICE = 2.0
MIN_AVERAGE_VOLUME = 1_000_000
MIN_MARKET_CAP = 300_000_000


def clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def score_market(quote: MarketQuote) -> tuple[float, list[str], list[str]]:
    """Score price action and liquidity, returning reasons and risks."""

    reasons: list[str] = []
    risks: list[str] = []

    if quote.price <= 0:
        return 0.0, reasons, ["Missing or invalid current price"]

    momentum = clamp((quote.price_change_pct + 5.0) / 10.0)
    if quote.price_change_pct >= 1.0:
        reasons.append(f"positive daily momentum ({quote.price_change_pct:.2f}%)")
    elif quote.price_change_pct <= -3.0:
        risks.append(f"weak daily momentum ({quote.price_change_pct:.2f}%)")

    if quote.average_volume > 0:
        relative_volume = quote.volume / quote.average_volume
    else:
        relative_volume = 0.0
        risks.append("missing average volume")

    volume_score = clamp(relative_volume / 2.0)
    if relative_volume >= 1.2:
        reasons.append(f"volume is {relative_volume:.1f}x recent average")
    elif relative_volume < 0.5:
        risks.append(f"thin trading today ({relative_volume:.1f}x average volume)")

    liquidity_score = 1.0
    if quote.price < MIN_PRICE:
        liquidity_score -= 0.35
        risks.append(f"price is below ${MIN_PRICE:.0f}")
    if quote.average_volume < MIN_AVERAGE_VOLUME:
        liquidity_score -= 0.35
        risks.append("average volume is below the liquidity threshold")
    if quote.market_cap is not None and quote.market_cap < MIN_MARKET_CAP:
        liquidity_score -= 0.3
        risks.append("market cap is below the risk threshold")

    liquidity_score = clamp(liquidity_score)
    return (0.5 * momentum) + (0.3 * volume_score) + (0.2 * liquidity_score), reasons, risks


def score_text_signal(signal: TextSignal, *, mention_scale: int) -> tuple[float, list[str], list[str]]:
    """Score mentions and sentiment from Reddit or news."""

    reasons: list[str] = []
    risks: list[str] = []
    mention_score = clamp(math.log1p(signal.mentions) / math.log1p(max(mention_scale, 1)))
    sentiment_score = clamp((signal.sentiment + 1.0) / 2.0)

    if signal.mentions > 0:
        reasons.append(f"{signal.mentions} tracked mention(s)")
    if signal.sentiment >= 0.25:
        reasons.append(f"positive text tone ({signal.sentiment:.2f})")
    elif signal.sentiment <= -0.25:
        risks.append(f"negative text tone ({signal.sentiment:.2f})")

    return (0.65 * mention_score) + (0.35 * sentiment_score), reasons, risks


def score_candidate(quote: MarketQuote, reddit_signal: TextSignal, news_signal: TextSignal) -> StockScore:
    """Build a ranked candidate from market, Reddit, and news inputs."""

    market_score, market_reasons, market_risks = score_market(quote)
    reddit_score, reddit_reasons, reddit_risks = score_text_signal(reddit_signal, mention_scale=25)
    news_score, news_reasons, news_risks = score_text_signal(news_signal, mention_scale=12)

    final_score = (0.45 * market_score) + (0.25 * reddit_score) + (0.30 * news_score)
    reasons = []
    risks = []

    reasons.extend(market_reasons)
    reasons.extend(f"Reddit: {reason}" for reason in reddit_reasons)
    reasons.extend(f"News: {reason}" for reason in news_reasons)
    risks.extend(market_risks)
    risks.extend(f"Reddit: {risk}" for risk in reddit_risks)
    risks.extend(f"News: {risk}" for risk in news_risks)

    if not reasons:
        reasons.append("balanced market, social, and news signals")

    return StockScore(
        ticker=quote.ticker,
        name=quote.name,
        price=quote.price,
        score=round(final_score, 4),
        reasons=tuple(reasons[:6]),
        risks=tuple(risks[:6]),
        market_quote=quote,
        reddit_signal=reddit_signal,
        news_signal=news_signal,
    )


def rank_candidates(
    quotes: list[MarketQuote],
    reddit_signals: dict[str, TextSignal],
    news_signals: dict[str, TextSignal],
    *,
    limit: int = 2,
) -> list[StockScore]:
    """Rank quotes and return the strongest candidates."""

    ranked = [
        score_candidate(
            quote,
            reddit_signals.get(quote.ticker, TextSignal(ticker=quote.ticker)),
            news_signals.get(quote.ticker, TextSignal(ticker=quote.ticker)),
        )
        for quote in quotes
    ]
    ranked.sort(key=lambda candidate: candidate.score, reverse=True)
    return ranked[:limit]


def rank_by_market(quotes: list[MarketQuote], *, limit: int) -> list[MarketQuote]:
    """Return quotes with the strongest standalone market scores."""

    ranked = sorted(quotes, key=lambda quote: score_market(quote)[0], reverse=True)
    return ranked[:limit]
