"""Network data collection for market quotes, Reddit posts, and headlines."""

from __future__ import annotations

import csv
import io
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from base64 import b64encode
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Iterable, Mapping

from stock_recommender.models import MarketQuote, TextSignal
from stock_recommender.sentiment import average_sentiment

DEFAULT_SUBREDDITS = ("stocks", "investing", "wallstreetbets", "StockMarket")
STOOQ_BATCH_SIZE = 150
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
            "Origin": "https://www.nasdaq.com",
            "Referer": "https://www.nasdaq.com/",
            "User-Agent": "Mozilla/5.0 (compatible; daily-stock-research-bot/1.0)",
        }

    def get_text(self, url: str, headers: Mapping[str, str] | None = None) -> str:
        request_headers = dict(self.headers)
        if headers:
            request_headers.update(headers)
        request = urllib.request.Request(url, headers=request_headers)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return response.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, TimeoutError) as exc:
            raise DataSourceError(f"Could not fetch {url}: {exc}") from exc

    def get_json(self, url: str, headers: Mapping[str, str] | None = None) -> dict:
        return json.loads(self.get_text(url, headers=headers))

    def post_json(self, url: str, data: Mapping[str, str], headers: Mapping[str, str] | None = None) -> dict:
        request_headers = dict(self.headers)
        request_headers["Content-Type"] = "application/x-www-form-urlencoded"
        if headers:
            request_headers.update(headers)
        encoded_data = urllib.parse.urlencode(data).encode("utf-8")
        request = urllib.request.Request(url, data=encoded_data, headers=request_headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8", errors="replace"))
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            raise DataSourceError(f"Could not post to {url}: {exc}") from exc


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


def fetch_stooq_quotes(
    tickers: Iterable[str],
    client: HttpClient | None = None,
    batch_size: int = STOOQ_BATCH_SIZE,
) -> list[MarketQuote]:
    """Fetch delayed batch quote data from Stooq's public CSV endpoint."""

    client = client or HttpClient()
    unique_tickers = sorted(set(ticker.upper() for ticker in tickers))
    if not unique_tickers:
        return []

    quotes: list[MarketQuote] = []
    errors: list[str] = []
    chunks = list(_chunked(unique_tickers, max(batch_size, 1)))

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(_fetch_stooq_quote_batch, chunk, client): chunk for chunk in chunks}
        for future in as_completed(futures):
            try:
                quotes.extend(future.result())
            except DataSourceError as exc:
                errors.append(str(exc))

    if errors and not quotes:
        raise DataSourceError("; ".join(errors[:3]))

    return sorted(quotes, key=lambda quote: quote.ticker)


def _fetch_stooq_quote_batch(tickers: list[str], client: HttpClient) -> list[MarketQuote]:
    stooq_symbols = [_to_stooq_symbol(ticker) for ticker in tickers]
    symbols = "+".join(stooq_symbols)
    csv_text = client.get_text(f"https://stooq.com/q/l/?s={symbols}&f=sd2t2ohlcv&h&e=csv")
    rows = csv.DictReader(io.StringIO(csv_text))
    quotes: list[MarketQuote] = []

    for row in rows:
        symbol = str(row.get("Symbol") or "")
        if not symbol or row.get("Date") == "N/D":
            continue

        ticker = _from_stooq_symbol(symbol)
        open_price = _float(row.get("Open"))
        close_price = _float(row.get("Close"))
        volume = _int(row.get("Volume"))
        if close_price <= 0:
            continue

        if open_price > 0:
            price_change_pct = ((close_price - open_price) / open_price) * 100.0
        else:
            price_change_pct = 0.0

        quotes.append(
            MarketQuote(
                ticker=ticker,
                name=ticker,
                price=close_price,
                price_change_pct=price_change_pct,
                volume=volume,
                average_volume=volume,
            )
        )

    return quotes


def fetch_nasdaq_quotes(tickers: Iterable[str], client: HttpClient | None = None) -> list[MarketQuote]:
    """Fetch current quote data from Nasdaq's public quote endpoints."""

    client = client or HttpClient()
    unique_tickers = sorted(set(ticker.upper() for ticker in tickers))
    quotes: list[MarketQuote] = []

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(_fetch_single_nasdaq_quote, ticker, client): ticker for ticker in unique_tickers}
        for future in as_completed(futures):
            quote = future.result()
            if quote:
                quotes.append(quote)

    return sorted(quotes, key=lambda quote: quote.ticker)


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
    reddit_headers = build_reddit_oauth_headers(client)
    base_url = "https://oauth.reddit.com" if reddit_headers else "https://www.reddit.com"

    for subreddit in subreddits:
        path = f"/r/{subreddit}/hot"
        suffix = "" if reddit_headers else ".json"
        url = f"{base_url}{path}{suffix}?limit={posts_per_subreddit}"
        try:
            payload = client.get_json(url, headers=reddit_headers)
        except (DataSourceError, ValueError):
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


def fetch_nasdaq_news_signals(
    tickers: Iterable[str],
    client: HttpClient | None = None,
    headlines_per_ticker: int = 8,
) -> dict[str, TextSignal]:
    """Fetch recent Nasdaq article titles related to each ticker."""

    client = client or HttpClient()
    unique_tickers = sorted(set(ticker.upper() for ticker in tickers))
    signals: dict[str, TextSignal] = {}

    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {
            executor.submit(_fetch_single_nasdaq_news_signal, ticker, client, headlines_per_ticker): ticker
            for ticker in unique_tickers
        }
        for future in as_completed(futures):
            signal = future.result()
            if signal and signal.mentions:
                signals[signal.ticker] = signal

    return signals


def fetch_google_news_signals(
    tickers: Iterable[str],
    client: HttpClient | None = None,
    headlines_per_ticker: int = 8,
) -> dict[str, TextSignal]:
    """Fetch ticker-specific Google News RSS headlines."""

    client = client or HttpClient()
    unique_tickers = sorted(set(ticker.upper() for ticker in tickers))
    signals: dict[str, TextSignal] = {}

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {
            executor.submit(_fetch_single_google_news_signal, ticker, client, headlines_per_ticker): ticker
            for ticker in unique_tickers
        }
        for future in as_completed(futures):
            signal = future.result()
            if signal and signal.mentions:
                signals[signal.ticker] = signal

    return signals


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


def build_reddit_oauth_headers(client: HttpClient) -> dict[str, str] | None:
    """Build OAuth headers when REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET exist."""

    client_id = os.getenv("REDDIT_CLIENT_ID")
    client_secret = os.getenv("REDDIT_CLIENT_SECRET")
    if not client_id or not client_secret:
        return None

    credentials = b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode("ascii")
    user_agent = os.getenv("REDDIT_USER_AGENT", "daily-stock-research-bot/1.0")
    try:
        token = client.post_json(
            "https://www.reddit.com/api/v1/access_token",
            {"grant_type": "client_credentials"},
            {"Authorization": f"Basic {credentials}", "User-Agent": user_agent},
        ).get("access_token")
    except DataSourceError:
        return None
    if not token:
        return None

    return {"Authorization": f"Bearer {token}", "User-Agent": user_agent}


def _fetch_single_nasdaq_news_signal(
    ticker: str,
    client: HttpClient,
    headlines_per_ticker: int,
) -> TextSignal | None:
    query = urllib.parse.urlencode({"q": f"{ticker}|stocks", "limit": str(headlines_per_ticker)})
    try:
        payload = client.get_json(f"https://api.nasdaq.com/api/news/topic/articlebysymbol?{query}")
    except (DataSourceError, ValueError):
        return None

    rows = (payload.get("data") or {}).get("rows", [])
    titles: list[str] = []
    for row in rows:
        title = str(row.get("title") or "").strip()
        if not title:
            continue
        if _nasdaq_row_mentions_ticker(row, ticker):
            titles.append(title)

    if not titles:
        return None

    return TextSignal(
        ticker=ticker,
        mentions=len(titles),
        sentiment=average_sentiment(titles),
        sample_titles=tuple(titles[:3]),
    )


def _nasdaq_row_mentions_ticker(row: dict, ticker: str) -> bool:
    primary = str(row.get("primarysymbol") or "").upper()
    related = [str(symbol).split("|", maxsplit=1)[0].upper() for symbol in row.get("related_symbols", [])]
    return ticker == primary or ticker in related


def _fetch_single_google_news_signal(
    ticker: str,
    client: HttpClient,
    headlines_per_ticker: int,
) -> TextSignal | None:
    query = urllib.parse.urlencode(
        {
            "q": f"{ticker} stock",
            "hl": "en-US",
            "gl": "US",
            "ceid": "US:en",
        }
    )
    try:
        rss = client.get_text(f"https://news.google.com/rss/search?{query}")
    except DataSourceError:
        return None

    headlines = parse_rss_titles(rss)[:headlines_per_ticker]
    if not headlines:
        return None

    return TextSignal(
        ticker=ticker,
        mentions=len(headlines),
        sentiment=average_sentiment(headlines),
        sample_titles=tuple(headlines[:3]),
    )


def _fetch_single_nasdaq_quote(ticker: str, client: HttpClient) -> MarketQuote | None:
    encoded_ticker = urllib.parse.quote(ticker, safe="")
    try:
        info = client.get_json(
            f"https://api.nasdaq.com/api/quote/{encoded_ticker}/info?assetclass=stocks"
        ).get("data")
        summary = client.get_json(
            f"https://api.nasdaq.com/api/quote/{encoded_ticker}/summary?assetclass=stocks"
        ).get("data")
    except (DataSourceError, ValueError):
        return None

    if not info:
        return None

    primary = info.get("primaryData") or {}
    summary_data = (summary or {}).get("summaryData") or {}
    price = _money(primary.get("lastSalePrice"))
    if price <= 0:
        return None

    average_volume = _summary_int(summary_data, "AverageVolume")
    volume = _int_from_string(primary.get("volume")) or _summary_int(summary_data, "ShareVolume")

    return MarketQuote(
        ticker=ticker,
        name=info.get("companyName") or ticker,
        price=price,
        price_change_pct=_percent(primary.get("percentageChange")),
        volume=volume,
        average_volume=average_volume or volume,
        market_cap=_summary_int(summary_data, "MarketCap") or None,
    )


def _to_stooq_symbol(ticker: str) -> str:
    return f"{ticker.lower()}.us"


def _from_stooq_symbol(symbol: str) -> str:
    return symbol.upper().removesuffix(".US")


def _chunked(items: list[str], size: int) -> list[list[str]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def _summary_int(summary_data: dict, key: str) -> int:
    row = summary_data.get(key) or {}
    return _int_from_string(row.get("value"))


def _money(value: object) -> float:
    if value is None:
        return 0.0
    text = str(value).replace("$", "").replace(",", "").strip()
    return _float(text)


def _percent(value: object) -> float:
    if value is None:
        return 0.0
    text = str(value).replace("%", "").replace("+", "").replace(",", "").strip()
    return _float(text)


def _int_from_string(value: object) -> int:
    if value is None:
        return 0
    text = str(value).replace("$", "").replace(",", "").strip()
    if text in {"", "N/A"}:
        return 0
    return _int(text)


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
