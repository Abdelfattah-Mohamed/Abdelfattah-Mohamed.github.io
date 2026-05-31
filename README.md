# Daily Stock Research Recommender

This repository now includes a small Python system that generates two daily stock research ideas from:

- Stooq delayed market quote data
- Reddit discussion from stock-related subreddits
- Google News RSS headlines

The output is a ranked Markdown report with reasons, risks, and sample signal titles.

> This tool is not personalized financial advice. It is an automated research screen. Review fundamentals, risk, position sizing, and your own financial situation before investing.

## Run locally

Python 3.10+ is enough; the tool uses only the standard library.

```bash
python3 daily_stock_recommendations.py
```

Write the report to a file:

```bash
python3 daily_stock_recommendations.py --output daily-stock-recommendations.md
```

Run without network access using deterministic sample data:

```bash
python3 daily_stock_recommendations.py --offline-sample
```

## Customize the stocks it can rank

Edit `config/watchlist.txt`. The system only recommends tickers from this watchlist, so keep it to liquid stocks or ETFs you are willing to research.

## Reddit access

Anonymous Reddit JSON requests are often blocked in hosted environments. For reliable Reddit signals, create a Reddit app and configure these repository or environment secrets before the scheduled job runs:

- `REDDIT_CLIENT_ID`
- `REDDIT_CLIENT_SECRET`
- `REDDIT_USER_AGENT` (optional, defaults to `daily-stock-research-bot/1.0`)

If those values are missing or Reddit blocks access, the recommender still runs and scores the market/news signals.

## Daily morning automation

`.github/workflows/daily-stock-recommendations.yml` runs the recommender every weekday at `12:00 UTC` and stores the Markdown report as a GitHub Actions artifact. Adjust the cron expression if your local morning is different.

## How scoring works

Each ticker receives a transparent score from:

1. market action: daily price move, volume vs. average volume, liquidity, and market cap
2. Reddit signal: mention count and simple sentiment from tracked posts
3. news signal: recent headline count and simple sentiment from Yahoo Finance RSS

The script returns the highest-scoring two candidates and includes risk notes when a stock has weak momentum, low liquidity, negative text tone, or small market cap.

## Files

- `daily_stock_recommendations.py` - command entry point
- `stock_recommender/` - data collection, sentiment, scoring, and reporting code
- `config/watchlist.txt` - editable ticker universe
- `tests/` - focused unit tests for scoring and parsing
