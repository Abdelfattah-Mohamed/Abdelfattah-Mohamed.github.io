import unittest

from stock_recommender.models import MarketQuote, TextSignal
from stock_recommender.scoring import rank_by_market, rank_candidates, score_candidate


class ScoringTest(unittest.TestCase):
    def test_rank_candidates_returns_highest_two_scores(self):
        quotes = [
            MarketQuote("AAA", "AAA Corp", 100.0, 2.0, 2_500_000, 1_500_000, 5_000_000_000),
            MarketQuote("BBB", "BBB Corp", 50.0, -4.0, 800_000, 2_000_000, 4_000_000_000),
            MarketQuote("CCC", "CCC Corp", 200.0, 3.0, 5_000_000, 2_000_000, 8_000_000_000),
        ]
        reddit = {
            "AAA": TextSignal("AAA", 5, 0.1),
            "BBB": TextSignal("BBB", 30, -0.7),
            "CCC": TextSignal("CCC", 20, 0.7),
        }
        news = {
            "AAA": TextSignal("AAA", 3, 0.2),
            "BBB": TextSignal("BBB", 10, -0.8),
            "CCC": TextSignal("CCC", 8, 0.6),
        }

        ranked = rank_candidates(quotes, reddit, news, limit=2)

        self.assertEqual([candidate.ticker for candidate in ranked], ["CCC", "AAA"])

    def test_score_candidate_adds_risk_for_low_liquidity(self):
        quote = MarketQuote("LOWQ", "Low Quality Corp", 1.25, -5.0, 10_000, 50_000, 50_000_000)

        candidate = score_candidate(
            quote,
            TextSignal("LOWQ", 1, 0.0),
            TextSignal("LOWQ", 1, 0.0),
        )

        self.assertTrue(any("price is below" in risk for risk in candidate.risks))
        self.assertTrue(any("average volume" in risk for risk in candidate.risks))
        self.assertTrue(any("market cap" in risk for risk in candidate.risks))

    def test_rank_by_market_limits_to_market_shortlist(self):
        quotes = [
            MarketQuote("SLOW", "Slow Corp", 20.0, -2.0, 1_000_000, 1_000_000),
            MarketQuote("FAST", "Fast Corp", 20.0, 4.0, 3_000_000, 1_000_000),
            MarketQuote("MID", "Mid Corp", 20.0, 1.0, 1_500_000, 1_000_000),
        ]

        ranked = rank_by_market(quotes, limit=2)

        self.assertEqual([quote.ticker for quote in ranked], ["FAST", "MID"])


if __name__ == "__main__":
    unittest.main()
