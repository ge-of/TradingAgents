import pytest
from unittest.mock import MagicMock

from tradingagents.batch.runner import BatchRunner, TickerResult, BatchResult


def _make_state(ticker, rating):
    return {
        "company_of_interest": ticker,
        "trade_date": "2026-05-04",
        "market_report": f"Market for {ticker}.",
        "sentiment_report": "",
        "news_report": "",
        "fundamentals_report": "",
        "investment_debate_state": {
            "bull_history": "", "bear_history": "",
            "history": [], "current_response": "", "judge_decision": "",
        },
        "trader_investment_plan": "",
        "risk_debate_state": {
            "aggressive_history": "", "conservative_history": "",
            "neutral_history": "", "history": [], "judge_decision": "",
        },
        "final_trade_decision": f"Rating: {rating}",
    }


class TestBatchRunnerSavesReports:
    def test_save_creates_summary_file(self, tmp_path):
        graph = MagicMock()
        graph.propagate.return_value = (
            _make_state("AAPL", "Buy"),
            "Buy",
        )
        config = {"batch_save_dir": str(tmp_path)}
        runner = BatchRunner(graph=graph, config=config)
        result = runner.run(["AAPL"], "2026-05-04")

        summary = tmp_path / "2026-05-04" / "summary.md"
        assert summary.exists()
        content = summary.read_text()
        assert "AAPL" in content

    def test_save_creates_per_ticker_files(self, tmp_path):
        graph = MagicMock()
        graph.propagate.side_effect = [
            (_make_state("AAPL", "Buy"), "Buy"),
            (_make_state("MSFT", "Hold"), "Hold"),
        ]
        config = {"batch_save_dir": str(tmp_path)}
        runner = BatchRunner(graph=graph, config=config)
        runner.run(["AAPL", "MSFT"], "2026-05-04")

        assert (tmp_path / "2026-05-04" / "AAPL.md").exists()
        assert (tmp_path / "2026-05-04" / "MSFT.md").exists()

    def test_no_save_when_batch_save_dir_not_set(self, tmp_path):
        graph = MagicMock()
        graph.propagate.return_value = (
            _make_state("AAPL", "Buy"),
            "Buy",
        )
        runner = BatchRunner(graph=graph, config={})
        result = runner.run(["AAPL"], "2026-05-04")
        assert len(list(tmp_path.iterdir())) == 0

    def test_unsafe_ticker_skipped_in_save(self, tmp_path):
        graph = MagicMock()
        graph.propagate.side_effect = [
            (_make_state("AAPL", "Buy"), "Buy"),
            (_make_state("../evil", "Hold"), "Hold"),
        ]
        config = {"batch_save_dir": str(tmp_path)}
        runner = BatchRunner(graph=graph, config=config)
        result = runner.run(["AAPL", "../evil"], "2026-05-04")
        assert (tmp_path / "2026-05-04" / "AAPL.md").exists()
        assert (tmp_path / "2026-05-04" / "summary.md").exists()
        saved_files = [f.name for f in (tmp_path / "2026-05-04").iterdir()]
        assert "evil.md" not in saved_files
        assert "..evil.md" not in saved_files
