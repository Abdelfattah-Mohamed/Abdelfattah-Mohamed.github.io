"""Network data collection for market quotes, Reddit posts, and headlines."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Iterable

from stock_recommender.models import MarketQuote, TextSignal
from stock_recommender.sentiment import average_sentiment

DEFAULT_SUBREDDITS = ("stocks", "investing", "wallstreetbets", "StockMarket")
COMMON_WORD_TICKERS = {
    "A",
    "AI",
    "ARE",
    "AT",
    "BE",
    "BY",
    "CAN",
    "DD",
    "FOR",
    "GO",
    "HAS",
    "HE",
    "IT",
    "ME",
    "ON",
    "OR",
    "SO",
    "TO",
    "UK",
    "US",
}


class DataSourceError(RuntimeError):
    """Raised when a remote source cannot be read."""


class HttpClient:
    """Tiny urllib wrapper with a finance-friendly user agent."""

    def __init__(self, timeout: int = 15) -> None:
        self.timeout = timeout
        self.headers = {
            "Accept": "application/json,text/xml,application/rss+xml,text/html",
            "User-Agent": "daily-stock-research-bot/1.0",
        }

    def get_text(self, url: str) -> str:
        request = urllib.request.Request(url, headers=self.headers)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return response.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, TimeoutError) as exc:
            raise DataSourceError(f"Could not fetch {url}: {exc}") from exc

    def get_json(self, url: str) -> dict:
        return json.loads(self.get_text(url))


def load_watchlist(path: Path) -> list[str]:
    """Load ticker symbols from a newline-delimited watchlist file."""

    tickers: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        ticker = line.strip().upper()
        if not ticker or ticker.startswith("#"):
            continue
        tickers.append(ticker)
    return sorted(set(tickers))


def fetch_yahoo_quotes(tickers: Iterable[str], client: HttpClient | None = None) -> list[MarketQuote]:
    """Fetch current quote data from Yahoo Finance's public quote endpoint."""

    client = client or HttpClient()
    symbols = ",".join(sorted(set(tickers)))
    if not symbols:
        return []

    query = urllib.parse.urlencode({"symbols": symbols})
    payload = client.get_json(f"https://query1.finance.yahoo.com/v7/finance/quote?{query}")
    rows = payload.get("quoteResponse", {}).get("result", [])

    quotes: list[MarketQuote] = []
    for row in rows:
        ticker = str(row.get("symbol", "")).upper()
        price = _float(row.get("regularMarketPrice"))
        if not ticker or price <= 0:
            continue

        quotes.append(
            MarketQuote(
                ticker=ticker,
                name=row.get("shortName") or row.get("longName") or ticker,
                price=price,
                price_change_pct=_float(row.get("regularMarketChangePercent")),
                volume=_int(row.get("regularMarketVolume")),
                average_volume=_int(row.get("averageDailyVolume3Month") or row.get("averageDailyVolume10Day")),
                market_cap=_optional_int(row.get("marketCap")),
            )
        )
    return quotes


def fetch_reddit_signals(
    tickers: Iterable[str],
    client: HttpClient | None = None,
    subreddits: tuple[str, ...] = DEFAULT_SUBREDDITS,
    posts_per_subreddit: int = 75,
) -> dict[str, TextSignal]:
    """Fetch public Reddit posts and summarize ticker mentions."""

    client = client or HttpClient()
    ticker_set = {ticker.upper() for ticker in tickers}
    tracked_texts: dict[str, list[str]] = {ticker: [] for ticker in ticker_set}

    for subreddit in subreddits:
        url = f"https://www.reddit.com/r/{subreddit}/hot.json?limit={posts_per_subreddit}"
        try:
            payload = client.get_json(url)
        except DataSourceError:
            continue

        for child in payload.get("data", {}).get("children", []):
            post = child.get("data", {})
            title = str(post.get("title") or "")
            body = str(post.get("selftext") or "")
            combined = f"{title}\n{body}"
            for ticker in extract_ticker_mentions(combined, ticker_set):
                tracked_texts[ticker].append(title)

    return {
        ticker: TextSignal(
            ticker=ticker,
            mentions=len(texts),
            sentiment=average_sentiment(texts),
            sample_titles=tuple(texts[:3]),
        )
        for ticker, texts in tracked_texts.items()
        if texts
    }


def fetch_yahoo_news_signals(
    tickers: Iterable[str],
    client: HttpClient | None = None,
    headlines_per_ticker: int = 8,
) -> dict[str, TextSignal]:
    """Fetch recent Yahoo Finance RSS headlines for each ticker."""

    client = client or HttpClient()
    signals: dict[str, TextSignal] = {}

    for ticker in sorted(set(tickers)):
        query = urllib.parse.urlencode({"s": ticker, "region": "US", "lang": "en-US"})
        url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?{query}"
        try:
            rss = client.get_text(url)
        except DataSourceError:
            continue

        headlines = parse_rss_titles(rss)[:headlines_per_ticker]
        if not headlines:
            continue

        signals[ticker] = TextSignal(
            ticker=ticker,
            mentions=len(headlines),
            sentiment=average_sentiment(headlines),
            sample_titles=tuple(headlines[:3]),
        )

    return signals


def extract_ticker_mentions(text: str, tickers: set[str]) -> set[str]:
    """Find ticker mentions as cashtags or uppercase words."""

    mentions: set[str] = set()
    cashtags = {match.upper() for match in re.findall(r"\$([A-Za-z]{1,5})\b", text)}
    uppercase_words = {
        match.upper()
        for match in re.findall(r"\b[A-Z]{2,5}\b", text)
        if match.upper() not in COMMON_WORD_TICKERS
    }

    for ticker in cashtags | uppercase_words:
        if ticker in tickers:
            mentions.add(ticker)
    return mentions


def parse_rss_titles(rss: str) -> list[str]:
    """Parse RSS item titles, tolerating malformed feeds by returning none."""

    try:
        root = ET.fromstring(rss)
    except ET.ParseError:
        return []

    titles: list[str] = []
    for item in root.findall(".//item"):
        title = item.findtext("title")
        if title:
            titles.append(title.strip())
    return titles


def _float(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _int(value: object) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    parsed = _int(value)
    return parsed if parsed > 0 else None
