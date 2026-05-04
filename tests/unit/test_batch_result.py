import pytest
from tradingagents.batch.runner import TickerResult, BatchResult


class TestTickerResult:
    def test_successful_result(self):
        r = TickerResult(
            ticker="AAPL",
            rating="Buy",
            final_state={"final_trade_decision": "Buy AAPL"},
        )
        assert r.ticker == "AAPL"
        assert r.rating == "Buy"
        assert r.error is None

    def test_failed_result(self):
        r = TickerResult(
            ticker="BAD",
            rating="Hold",
            final_state={},
            error="API timeout",
        )
        assert r.error == "API timeout"


class TestBatchResult:
    @pytest.fixture()
    def batch(self):
        return BatchResult(
            date="2026-05-04",
            results=[
                TickerResult("AAPL", "Buy", {"final_trade_decision": "Buy"}),
                TickerResult("MSFT", "Hold", {"final_trade_decision": "Hold"}),
                TickerResult("GOOGL", "Sell", {"final_trade_decision": "Sell"}),
                TickerResult("NVDA", "Overweight", {"final_trade_decision": "Overweight"}),
                TickerResult("AMZN", "Underweight", {"final_trade_decision": "Underweight"}),
                TickerResult("BAD", "Hold", {}, error="failed"),
            ],
        )

    def test_ranked_ordering(self, batch):
        ranked = batch.ranked()
        ratings = [r.rating for r in ranked]
        assert ratings == ["Buy", "Overweight", "Hold", "Hold", "Underweight", "Sell"]

    def test_buys_returns_buy_and_overweight(self, batch):
        buys = batch.buys()
        tickers = {r.ticker for r in buys}
        assert tickers == {"AAPL", "NVDA"}

    def test_successful_excludes_errors(self, batch):
        ok = batch.successful()
        assert all(r.error is None for r in ok)
        assert len(ok) == 5

    def test_failed_includes_only_errors(self, batch):
        bad = batch.failed()
        assert len(bad) == 1
        assert bad[0].ticker == "BAD"
