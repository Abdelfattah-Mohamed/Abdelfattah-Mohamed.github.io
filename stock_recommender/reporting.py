"""Markdown and console output for recommendation reports."""

from __future__ import annotations

from stock_recommender.models import RecommendationReport, StockScore


def render_markdown(report: RecommendationReport) -> str:
    """Render a daily recommendation report as Markdown."""

    lines = [
        "# Daily Stock Research Ideas",
        "",
        f"Generated at: {report.generated_at.isoformat()}",
        f"Candidates considered: {report.considered_count}",
        "",
        f"> {report.disclaimer}",
        "",
    ]

    if not report.recommendations:
        lines.extend(
            [
                "No recommendations were produced today.",
                "",
                "Check data-source availability and the watchlist configuration.",
            ]
        )
        return "\n".join(lines) + "\n"

    for index, recommendation in enumerate(report.recommendations, start=1):
        lines.extend(render_recommendation(index, recommendation))
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def render_recommendation(index: int, recommendation: StockScore) -> list[str]:
    """Render a single ranked stock idea."""

    quote = recommendation.market_quote
    lines = [
        f"## {index}. {recommendation.ticker} - {recommendation.name}",
        "",
        f"- Score: {recommendation.score:.2f}",
        f"- Last price: ${recommendation.price:,.2f}",
        f"- Daily move: {quote.price_change_pct:.2f}%",
        f"- Volume: {quote.volume:,} vs. {quote.average_volume:,} average",
        f"- Reddit mentions tracked: {recommendation.reddit_signal.mentions}",
        f"- News headlines tracked: {recommendation.news_signal.mentions}",
        "",
        "Why it ranked:",
    ]
    lines.extend(f"- {reason}" for reason in recommendation.reasons)

    if recommendation.risks:
        lines.append("")
        lines.append("Risks to review:")
        lines.extend(f"- {risk}" for risk in recommendation.risks)

    samples = list(recommendation.news_signal.sample_titles[:2]) + list(
        recommendation.reddit_signal.sample_titles[:2]
    )
    if samples:
        lines.append("")
        lines.append("Sample signal titles:")
        lines.extend(f"- {sample}" for sample in samples[:4])

    return lines
