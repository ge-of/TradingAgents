"""End-to-end test of the batch pipeline with mocked LLM."""
import pytest
from unittest.mock import MagicMock

from tradingagents.batch import BatchRunner, BatchResult, TickerResult
from tradingagents.batch.report import generate_summary_report, generate_ticker_report


def _make_state(ticker, rating):
    return {
        "company_of_interest": ticker,
        "trade_date": "2026-05-04",
        "market_report": f"Market analysis for {ticker}.",
        "sentiment_report": f"Sentiment for {ticker}.",
        "news_report": f"News for {ticker}.",
        "fundamentals_report": f"Fundamentals for {ticker}.",
        "investment_debate_state": {
            "bull_history": f"Bull for {ticker}.",
            "bear_history": f"Bear for {ticker}.",
            "history": [],
            "current_response": "",
            "judge_decision": f"Research decision for {ticker}.",
        },
        "trader_investment_plan": f"Plan for {ticker}.",
        "risk_debate_state": {
            "aggressive_history": f"Aggressive for {ticker}.",
            "conservative_history": f"Conservative for {ticker}.",
            "neutral_history": f"Neutral for {ticker}.",
            "history": [],
            "judge_decision": f"PM decision for {ticker}.",
        },
        "final_trade_decision": f"Rating: {rating}\nDetailed analysis for {ticker}.",
    }


class TestBatchIntegration:
    def test_full_pipeline(self, tmp_path):
        graph = MagicMock()
        graph.propagate.side_effect = [
            (_make_state("AAPL", "Buy"), "Buy"),
            Exception("Network error"),
            (_make_state("GOOGL", "Overweight"), "Overweight"),
            (_make_state("MSFT", "Sell"), "Sell"),
        ]

        config = {"batch_save_dir": str(tmp_path)}
        runner = BatchRunner(graph=graph, config=config)
        result = runner.run(["AAPL", "BAD", "GOOGL", "MSFT"], "2026-05-04")

        assert isinstance(result, BatchResult)
        assert len(result.results) == 4
        assert len(result.successful()) == 3
        assert len(result.failed()) == 1

        ranked = result.ranked()
        ratings = [r.rating for r in ranked if r.error is None]
        assert ratings == ["Buy", "Overweight", "Sell"]

        buys = result.buys()
        assert {r.ticker for r in buys} == {"AAPL", "GOOGL"}

        summary_path = tmp_path / "2026-05-04" / "summary.md"
        assert summary_path.exists()
        summary = summary_path.read_text()
        assert "AAPL" in summary
        assert "GOOGL" in summary
        assert "Network error" in summary

        assert (tmp_path / "2026-05-04" / "AAPL.md").exists()
        assert (tmp_path / "2026-05-04" / "GOOGL.md").exists()
        assert (tmp_path / "2026-05-04" / "MSFT.md").exists()
        assert (tmp_path / "2026-05-04" / "BAD.md").exists()

        bad_report = (tmp_path / "2026-05-04" / "BAD.md").read_text()
        assert "Network error" in bad_report

    def test_imports_from_package(self):
        from tradingagents.batch import BatchRunner, TickerResult, BatchResult
        assert BatchRunner is not None
        assert TickerResult is not None
        assert BatchResult is not None
