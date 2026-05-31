import unittest

from stock_recommender.data_sources import extract_ticker_mentions, parse_rss_titles


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


if __name__ == "__main__":
    unittest.main()
