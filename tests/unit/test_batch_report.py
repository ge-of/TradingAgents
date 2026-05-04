import pytest

from tradingagents.batch.runner import TickerResult, BatchResult
from tradingagents.batch.report import generate_summary_report, generate_ticker_report


def _make_state(ticker, rating):
    return {
        "company_of_interest": ticker,
        "trade_date": "2026-05-04",
        "market_report": f"Market analysis for {ticker}.",
        "sentiment_report": f"Sentiment analysis for {ticker}.",
        "news_report": f"News analysis for {ticker}.",
        "fundamentals_report": f"Fundamentals analysis for {ticker}.",
        "investment_debate_state": {
            "bull_history": f"Bull case for {ticker}.",
            "bear_history": f"Bear case for {ticker}.",
            "history": [],
            "current_response": "",
            "judge_decision": f"Research decision for {ticker}.",
        },
        "trader_investment_plan": f"Trading plan for {ticker}.",
        "risk_debate_state": {
            "aggressive_history": f"Aggressive view on {ticker}.",
            "conservative_history": f"Conservative view on {ticker}.",
            "neutral_history": f"Neutral view on {ticker}.",
            "history": [],
            "judge_decision": f"Final decision: {rating} for {ticker}.",
        },
        "final_trade_decision": f"Rating: {rating}\nFull decision for {ticker}.",
    }


class TestGenerateSummaryReport:
    def test_contains_ranking_table_with_decision(self):
        batch = BatchResult(
            date="2026-05-04",
            results=[
                TickerResult("AAPL", "Buy", _make_state("AAPL", "Buy")),
                TickerResult("MSFT", "Hold", _make_state("MSFT", "Hold")),
            ],
        )
        md = generate_summary_report(batch)
        assert "| Ticker | Rating | Decision |" in md
        assert "| AAPL" in md
        assert "| MSFT" in md
        assert "Full decision for AAPL" in md

    def test_contains_date(self):
        batch = BatchResult(date="2026-05-04", results=[])
        md = generate_summary_report(batch)
        assert "2026-05-04" in md

    def test_errors_section_when_failures_exist(self):
        batch = BatchResult(
            date="2026-05-04",
            results=[
                TickerResult("BAD", "Hold", {}, error="timeout"),
            ],
        )
        md = generate_summary_report(batch)
        assert "BAD" in md
        assert "timeout" in md

    def test_no_errors_section_when_all_succeed(self):
        batch = BatchResult(
            date="2026-05-04",
            results=[
                TickerResult("AAPL", "Buy", _make_state("AAPL", "Buy")),
            ],
        )
        md = generate_summary_report(batch)
        assert "Errors" not in md


class TestGenerateTickerReport:
    def test_contains_all_sections(self):
        state = _make_state("AAPL", "Buy")
        result = TickerResult("AAPL", "Buy", state)
        md = generate_ticker_report(result)
        assert "AAPL" in md
        assert "Market analysis" in md
        assert "Bull case" in md
        assert "Bear case" in md
        assert "Trading plan" in md
        assert "Aggressive view" in md
        assert "Conservative view" in md

    def test_error_result_produces_error_report(self):
        result = TickerResult("BAD", "Hold", {}, error="API failure")
        md = generate_ticker_report(result)
        assert "BAD" in md
        assert "API failure" in md
