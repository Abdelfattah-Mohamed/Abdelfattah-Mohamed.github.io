"""Command-line entry point for the daily stock recommender."""

from __future__ import annotations

import argparse
from pathlib import Path

from stock_recommender.data_sources import (
    DataSourceError,
    fetch_reddit_signals,
    fetch_yahoo_news_signals,
    fetch_yahoo_quotes,
    load_watchlist,
)
from stock_recommender.models import MarketQuote, RecommendationReport, TextSignal
from stock_recommender.reporting import render_markdown
from stock_recommender.scoring import rank_candidates

DEFAULT_WATCHLIST = Path("config/watchlist.txt")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate two daily stock research ideas from market, Reddit, and news signals."
    )
    parser.add_argument(
        "--watchlist",
        type=Path,
        default=DEFAULT_WATCHLIST,
        help="Path to a newline-delimited ticker watchlist.",
    )
    parser.add_argument("--limit", type=int, default=2, help="Number of ideas to return.")
    parser.add_argument("--output", type=Path, help="Optional Markdown output file.")
    parser.add_argument(
        "--offline-sample",
        action="store_true",
        help="Use bundled sample data instead of live web sources.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    if args.offline_sample:
        quotes, reddit_signals, news_signals = sample_inputs()
    else:
        tickers = load_watchlist(args.watchlist)
        try:
            quotes = fetch_yahoo_quotes(tickers)
        except DataSourceError as exc:
            raise SystemExit(f"Market quote fetch failed: {exc}") from exc

        quote_tickers = [quote.ticker for quote in quotes]
        reddit_signals = fetch_reddit_signals(quote_tickers)
        news_signals = fetch_yahoo_news_signals(quote_tickers)

    recommendations = tuple(
        rank_candidates(quotes, reddit_signals, news_signals, limit=max(args.limit, 1))
    )
    report = RecommendationReport.now(recommendations, considered_count=len(quotes))
    markdown = render_markdown(report)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(markdown, encoding="utf-8")

    print(markdown)
    return 0


def sample_inputs() -> tuple[list[MarketQuote], dict[str, TextSignal], dict[str, TextSignal]]:
    """Provide deterministic data for demos, tests, and offline runs."""

    quotes = [
        MarketQuote(
            ticker="MSFT",
            name="Microsoft Corporation",
            price=430.25,
            price_change_pct=1.7,
            volume=31_200_000,
            average_volume=24_000_000,
            market_cap=3_200_000_000_000,
        ),
        MarketQuote(
            ticker="NVDA",
            name="NVIDIA Corporation",
            price=1_045.50,
            price_change_pct=2.9,
            volume=45_000_000,
            average_volume=38_000_000,
            market_cap=2_500_000_000_000,
        ),
        MarketQuote(
            ticker="TSLA",
            name="Tesla, Inc.",
            price=178.90,
            price_change_pct=-2.2,
            volume=80_000_000,
            average_volume=95_000_000,
            market_cap=570_000_000_000,
        ),
    ]
    reddit_signals = {
        "MSFT": TextSignal("MSFT", 8, 0.35, ("MSFT cloud growth looks strong",)),
        "NVDA": TextSignal("NVDA", 17, 0.55, ("NVDA rally after bullish analyst upgrade",)),
        "TSLA": TextSignal("TSLA", 21, -0.20, ("TSLA demand concerns after price cuts",)),
    }
    news_signals = {
        "MSFT": TextSignal("MSFT", 6, 0.45, ("Microsoft beats cloud expectations",)),
        "NVDA": TextSignal("NVDA", 7, 0.60, ("NVIDIA gains on record AI demand",)),
        "TSLA": TextSignal("TSLA", 8, -0.35, ("Tesla falls after margin warning",)),
    }
    return quotes, reddit_signals, news_signals


if __name__ == "__main__":
    raise SystemExit(main())
