import pytest
from unittest.mock import MagicMock, patch
from typer.testing import CliRunner

from cli.main import app


runner = CliRunner()


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


class TestBatchCLI:
    @patch("tradingagents.batch.runner.TradingAgentsGraph")
    def test_batch_command_exists(self, mock_graph_cls):
        mock_graph = MagicMock()
        mock_graph.propagate.return_value = (
            _make_state("AAPL", "Buy"),
            "Buy",
        )
        mock_graph_cls.return_value = mock_graph
        result = runner.invoke(app, [
            "batch",
            "--tickers", "AAPL",
            "--date", "2026-05-04",
        ])
        assert result.exit_code == 0, result.output

    def test_batch_requires_tickers(self):
        result = runner.invoke(app, ["batch", "--date", "2026-05-04"])
        assert result.exit_code != 0

    def test_batch_rejects_invalid_date(self):
        result = runner.invoke(app, [
            "batch",
            "--tickers", "AAPL",
            "--date", "not-a-date",
        ])
        assert result.exit_code != 0
        assert "Invalid date" in result.output

    @patch("tradingagents.batch.runner.TradingAgentsGraph")
    def test_batch_output_contains_table(self, mock_graph_cls):
        mock_graph = MagicMock()
        mock_graph.propagate.side_effect = [
            (_make_state("AAPL", "Buy"), "Buy"),
            (_make_state("MSFT", "Sell"), "Sell"),
        ]
        mock_graph_cls.return_value = mock_graph
        result = runner.invoke(app, [
            "batch",
            "--tickers", "AAPL,MSFT",
            "--date", "2026-05-04",
        ])
        assert result.exit_code == 0
        assert "AAPL" in result.output
        assert "MSFT" in result.output
