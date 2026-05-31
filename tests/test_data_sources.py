import unittest

from stock_recommender.data_sources import extract_ticker_mentions, fetch_stooq_quotes, parse_rss_titles


class FakeStooqClient:
    def __init__(self):
        self.urls = []

    def get_text(self, url):
        self.urls.append(url)
        symbol_query = url.split("s=", maxsplit=1)[1].split("&", maxsplit=1)[0]
        rows = ["Symbol,Date,Time,Open,High,Low,Close,Volume"]
        for symbol in symbol_query.split("+"):
            rows.append(f"{symbol.upper()},2026-05-29,22:00:00,10,11,9,10.5,1234567")
        return "\n".join(rows)


class DataSourcesTest(unittest.TestCase):
    def test_extract_ticker_mentions_tracks_cashtags_and_uppercase_words(self):
        tickers = {"AAPL", "MSFT", "AI"}
        text = "Watching $AAPL and MSFT today, but AI as a common phrase is noisy."

        self.assertEqual(extract_ticker_mentions(text, tickers), {"AAPL", "MSFT"})

    def test_parse_rss_titles_returns_item_titles(self):
        rss = """<?xml version="1.0"?>
        <rss><channel>
          <item><title>Company beats expectations</title></item>
          <item><title>Analyst upgrade drives rally</title></item>
        </channel></rss>
        """

        self.assertEqual(
            parse_rss_titles(rss),
            [
                "Company beats expectations",
                "Analyst upgrade drives rally",
            ],
        )

    def test_fetch_stooq_quotes_batches_large_watchlists(self):
        client = FakeStooqClient()

        quotes = fetch_stooq_quotes(["AAA", "BBB", "CCC"], client=client, batch_size=2)

        self.assertEqual([quote.ticker for quote in quotes], ["AAA", "BBB", "CCC"])
        self.assertEqual(len(client.urls), 2)


if __name__ == "__main__":
    unittest.main()
