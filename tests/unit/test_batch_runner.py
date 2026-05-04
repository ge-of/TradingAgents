import pytest
from unittest.mock import MagicMock, patch, call

from tradingagents.batch.runner import BatchRunner, TickerResult, BatchResult


@pytest.fixture()
def mock_graph():
    graph = MagicMock()
    graph.propagate.side_effect = lambda ticker, date: (
        {"final_trade_decision": f"Rating: Buy\nAnalysis of {ticker}"},
        "Buy",
    )
    return graph


class TestBatchRunner:
    def test_run_returns_batch_result(self, mock_graph):
        runner = BatchRunner(graph=mock_graph)
        result = runner.run(["AAPL", "MSFT"], "2026-05-04")

        assert isinstance(result, BatchResult)
        assert result.date == "2026-05-04"
        assert len(result.results) == 2
        assert result.results[0].ticker == "AAPL"
        assert result.results[0].rating == "Buy"

    def test_run_calls_propagate_for_each_ticker(self, mock_graph):
        runner = BatchRunner(graph=mock_graph)
        runner.run(["AAPL", "MSFT", "GOOGL"], "2026-05-04")
        assert mock_graph.propagate.call_count == 3
        mock_graph.propagate.assert_has_calls([
            call("AAPL", "2026-05-04"),
            call("MSFT", "2026-05-04"),
            call("GOOGL", "2026-05-04"),
        ])

    def test_fault_isolation_continues_on_error(self, mock_graph):
        mock_graph.propagate.side_effect = [
            ({"final_trade_decision": "Rating: Buy"}, "Buy"),
            Exception("LLM timeout"),
            ({"final_trade_decision": "Rating: Sell"}, "Sell"),
        ]
        runner = BatchRunner(graph=mock_graph)
        result = runner.run(["AAPL", "BAD", "GOOGL"], "2026-05-04")
        assert len(result.results) == 3
        assert result.results[0].rating == "Buy"
        assert result.results[1].error == "LLM timeout"
        assert result.results[1].rating == "Hold"
        assert result.results[2].rating == "Sell"

    def test_run_empty_list(self, mock_graph):
        runner = BatchRunner(graph=mock_graph)
        result = runner.run([], "2026-05-04")
        assert len(result.results) == 0
        mock_graph.propagate.assert_not_called()

    def test_run_invokes_on_ticker_start_callback(self, mock_graph):
        calls = []
        runner = BatchRunner(graph=mock_graph)
        result = runner.run(
            ["AAPL", "MSFT"],
            "2026-05-04",
            on_ticker_start=lambda t, i, n: calls.append((t, i, n)),
        )
        assert calls == [("AAPL", 0, 2), ("MSFT", 1, 2)]

    def test_run_invokes_on_ticker_done_callback(self, mock_graph):
        calls = []
        runner = BatchRunner(graph=mock_graph)
        result = runner.run(
            ["AAPL"],
            "2026-05-04",
            on_ticker_done=lambda tr: calls.append(tr.ticker),
        )
        assert calls == ["AAPL"]
