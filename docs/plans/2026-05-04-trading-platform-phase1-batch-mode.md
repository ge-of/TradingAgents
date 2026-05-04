---
initiative: trading-platform
phase: 1
status: planned
worktree: main
depends_on: []
---

# Trading Platform Phase 1: Batch Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run the existing agent pipeline across multiple tickers in a single invocation, collect structured results, and output a ranked summary report.

**Architecture:** New `tradingagents/batch/` package with `BatchRunner` (sequential ticker loop over `TradingAgentsGraph.propagate()`) and `report.py` (markdown generation). Results stored in `TickerResult`/`BatchResult` dataclasses. A new `batch` CLI command wired into the existing Typer app.

**Tech Stack:** Python dataclasses, existing `TradingAgentsGraph`, `rating.py:parse_rating`, Rich tables, Typer CLI, pytest

---

### Task 1: TickerResult and BatchResult Dataclasses

**Files:**
- Create: `tradingagents/batch/__init__.py`
- Create: `tradingagents/batch/runner.py`
- Test: `tests/unit/test_batch_result.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_batch_result.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/geoffmiles/claude/repos/projects/TradingAgents && .venv/bin/python -m pytest tests/unit/test_batch_result.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tradingagents.batch'`

- [ ] **Step 3: Write minimal implementation**

Create `tradingagents/batch/__init__.py`:

```python
from tradingagents.batch.runner import TickerResult, BatchResult

__all__ = ["TickerResult", "BatchResult"]
```

Create `tradingagents/batch/runner.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from tradingagents.agents.utils.rating import RATINGS_5_TIER


@dataclass
class TickerResult:
    ticker: str
    rating: str
    final_state: Dict[str, Any]
    error: Optional[str] = None


_RATING_ORDER = {r: i for i, r in enumerate(RATINGS_5_TIER)}


@dataclass
class BatchResult:
    date: str
    results: List[TickerResult] = field(default_factory=list)

    def ranked(self) -> List[TickerResult]:
        return sorted(self.results, key=lambda r: _RATING_ORDER.get(r.rating, 2))

    def buys(self) -> List[TickerResult]:
        return [r for r in self.results if r.rating in ("Buy", "Overweight")]

    def successful(self) -> List[TickerResult]:
        return [r for r in self.results if r.error is None]

    def failed(self) -> List[TickerResult]:
        return [r for r in self.results if r.error is not None]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/geoffmiles/claude/repos/projects/TradingAgents && .venv/bin/python -m pytest tests/unit/test_batch_result.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add tradingagents/batch/__init__.py tradingagents/batch/runner.py tests/unit/test_batch_result.py
git commit -m "feat(batch): add TickerResult and BatchResult dataclasses"
```

---

### Task 2: BatchRunner.run() with Fault Isolation

**Files:**
- Modify: `tradingagents/batch/runner.py`
- Modify: `tradingagents/default_config.py` (add `batch_save_dir`)
- Test: `tests/unit/test_batch_runner.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_batch_runner.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/geoffmiles/claude/repos/projects/TradingAgents && .venv/bin/python -m pytest tests/unit/test_batch_runner.py -v`
Expected: FAIL with `AttributeError: type object 'BatchRunner' has no attribute ...` (class exists but has no `run` method)

- [ ] **Step 3: Add `batch_save_dir` to default config**

In `tradingagents/default_config.py`, add a new key after `"memory_log_max_entries"`:

```python
    "batch_save_dir": os.getenv(
        "TRADINGAGENTS_BATCH_DIR",
        os.path.join(_TRADINGAGENTS_HOME, "logs", "batch"),
    ),
```

- [ ] **Step 4: Implement BatchRunner.run()**

Update `tradingagents/batch/runner.py` — add to the existing file after the `BatchResult` class:

```python
import logging
from typing import Callable

logger = logging.getLogger(__name__)


class BatchRunner:
    def __init__(self, config=None, graph=None):
        from tradingagents.default_config import DEFAULT_CONFIG

        self.config = config or DEFAULT_CONFIG.copy()
        if graph is not None:
            self.graph = graph
        else:
            from tradingagents.graph.trading_graph import TradingAgentsGraph
            self.graph = TradingAgentsGraph(config=self.config)

    def run(
        self,
        tickers: List[str],
        date: str,
        on_ticker_start: Optional[Callable] = None,
        on_ticker_done: Optional[Callable] = None,
    ) -> BatchResult:
        batch = BatchResult(date=date)
        for i, ticker in enumerate(tickers):
            if on_ticker_start:
                on_ticker_start(ticker, i, len(tickers))
            try:
                final_state, rating = self.graph.propagate(ticker, date)
                result = TickerResult(
                    ticker=ticker,
                    rating=rating,
                    final_state=final_state,
                )
            except Exception as e:
                logger.error("Ticker %s failed: %s", ticker, e)
                result = TickerResult(
                    ticker=ticker,
                    rating="Hold",
                    final_state={},
                    error=str(e),
                )
            batch.results.append(result)
            if on_ticker_done:
                on_ticker_done(result)
        return batch
```

Update `tradingagents/batch/__init__.py` to export `BatchRunner`:

```python
from tradingagents.batch.runner import BatchRunner, TickerResult, BatchResult

__all__ = ["BatchRunner", "TickerResult", "BatchResult"]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/geoffmiles/claude/repos/projects/TradingAgents && .venv/bin/python -m pytest tests/unit/test_batch_runner.py -v`
Expected: All 6 tests PASS

- [ ] **Step 6: Commit**

```bash
git add tradingagents/batch/runner.py tradingagents/default_config.py tests/unit/test_batch_runner.py
git commit -m "feat(batch): implement BatchRunner.run() with fault isolation"
```

---

### Task 3: Report Generation

**Files:**
- Create: `tradingagents/batch/report.py`
- Test: `tests/unit/test_batch_report.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_batch_report.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/geoffmiles/claude/repos/projects/TradingAgents && .venv/bin/python -m pytest tests/unit/test_batch_report.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tradingagents.batch.report'`

- [ ] **Step 3: Implement report generation**

Create `tradingagents/batch/report.py`:

```python
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tradingagents.batch.runner import BatchResult, TickerResult


def _extract_decision_summary(result: TickerResult, max_len: int = 80) -> str:
    """Extract a short decision summary from final_trade_decision for the table."""
    decision = result.final_state.get("final_trade_decision", "")
    lines = [l.strip() for l in decision.splitlines() if l.strip() and not l.strip().lower().startswith("rating")]
    summary = " ".join(lines)
    if len(summary) > max_len:
        summary = summary[:max_len - 3] + "..."
    return summary or "N/A"


def generate_summary_report(batch: BatchResult) -> str:
    lines = [
        f"# Batch Analysis Summary",
        f"",
        f"**Date:** {batch.date}",
        f"**Tickers analyzed:** {len(batch.results)}",
        f"",
    ]

    successful = batch.successful()
    if successful:
        ranked = batch.ranked()
        ranked_ok = [r for r in ranked if r.error is None]
        lines.append("## Rankings")
        lines.append("")
        lines.append("| Ticker | Rating | Decision |")
        lines.append("|--------|--------|----------|")
        for r in ranked_ok:
            decision = _extract_decision_summary(r)
            lines.append(f"| {r.ticker} | {r.rating} | {decision} |")
        lines.append("")

    failed = batch.failed()
    if failed:
        lines.append("## Errors")
        lines.append("")
        for r in failed:
            lines.append(f"- **{r.ticker}:** {r.error}")
        lines.append("")

    return "\n".join(lines)


def generate_ticker_report(result: TickerResult) -> str:
    if result.error:
        return (
            f"# {result.ticker} Analysis Report\n\n"
            f"**Status:** Failed\n\n"
            f"**Error:** {result.error}\n"
        )

    state = result.final_state
    sections = [f"# {result.ticker} Analysis Report"]
    sections.append(f"\n**Rating:** {result.rating}")
    sections.append(f"**Date:** {state.get('trade_date', 'N/A')}\n")

    if state.get("market_report"):
        sections.append(f"## Market Analysis\n\n{state['market_report']}")

    if state.get("sentiment_report"):
        sections.append(f"## Sentiment Analysis\n\n{state['sentiment_report']}")

    if state.get("news_report"):
        sections.append(f"## News Analysis\n\n{state['news_report']}")

    if state.get("fundamentals_report"):
        sections.append(f"## Fundamentals Analysis\n\n{state['fundamentals_report']}")

    debate = state.get("investment_debate_state", {})
    if debate.get("bull_history") or debate.get("bear_history"):
        parts = []
        if debate.get("bull_history"):
            parts.append(f"### Bull Case\n\n{debate['bull_history']}")
        if debate.get("bear_history"):
            parts.append(f"### Bear Case\n\n{debate['bear_history']}")
        if debate.get("judge_decision"):
            parts.append(f"### Research Manager Decision\n\n{debate['judge_decision']}")
        sections.append(f"## Investment Debate\n\n" + "\n\n".join(parts))

    if state.get("trader_investment_plan"):
        sections.append(f"## Trading Plan\n\n{state['trader_investment_plan']}")

    risk = state.get("risk_debate_state", {})
    if risk.get("aggressive_history") or risk.get("conservative_history"):
        parts = []
        if risk.get("aggressive_history"):
            parts.append(f"### Aggressive Analyst\n\n{risk['aggressive_history']}")
        if risk.get("conservative_history"):
            parts.append(f"### Conservative Analyst\n\n{risk['conservative_history']}")
        if risk.get("neutral_history"):
            parts.append(f"### Neutral Analyst\n\n{risk['neutral_history']}")
        if risk.get("judge_decision"):
            parts.append(f"### Portfolio Manager Decision\n\n{risk['judge_decision']}")
        sections.append(f"## Risk Assessment\n\n" + "\n\n".join(parts))

    if state.get("final_trade_decision"):
        sections.append(f"## Final Decision\n\n{state['final_trade_decision']}")

    return "\n\n".join(sections) + "\n"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/geoffmiles/claude/repos/projects/TradingAgents && .venv/bin/python -m pytest tests/unit/test_batch_report.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add tradingagents/batch/report.py tests/unit/test_batch_report.py
git commit -m "feat(batch): add markdown report generation for batch results"
```

---

### Task 4: BatchRunner Saves Reports to Disk

**Files:**
- Modify: `tradingagents/batch/runner.py`
- Test: `tests/unit/test_batch_save.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_batch_save.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/geoffmiles/claude/repos/projects/TradingAgents && .venv/bin/python -m pytest tests/unit/test_batch_save.py -v`
Expected: FAIL (summary file not created — `run()` doesn't save reports yet)

- [ ] **Step 3: Add save logic to BatchRunner.run()**

Update `tradingagents/batch/runner.py` — add `_save_reports` method and call it at the end of `run()`:

```python
from pathlib import Path
from tradingagents.batch.report import generate_summary_report, generate_ticker_report
from tradingagents.dataflows.utils import safe_ticker_component


class BatchRunner:
    # ... existing __init__ and run() ...

    def run(self, tickers, date, on_ticker_start=None, on_ticker_done=None):
        # ... existing loop code ...
        self._save_reports(batch)
        return batch

    def _save_reports(self, batch: BatchResult) -> None:
        save_dir = self.config.get("batch_save_dir")
        if not save_dir:
            return
        out = Path(save_dir) / batch.date
        out.mkdir(parents=True, exist_ok=True)

        (out / "summary.md").write_text(
            generate_summary_report(batch), encoding="utf-8"
        )
        for result in batch.results:
            try:
                safe = safe_ticker_component(result.ticker)
            except ValueError:
                logger.warning("Skipping report save for unsafe ticker: %s", result.ticker)
                continue
            (out / f"{safe}.md").write_text(
                generate_ticker_report(result), encoding="utf-8"
            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/geoffmiles/claude/repos/projects/TradingAgents && .venv/bin/python -m pytest tests/unit/test_batch_save.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Run all batch tests together**

Run: `cd /Users/geoffmiles/claude/repos/projects/TradingAgents && .venv/bin/python -m pytest tests/unit/test_batch_result.py tests/unit/test_batch_runner.py tests/unit/test_batch_report.py tests/unit/test_batch_save.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add tradingagents/batch/runner.py tests/unit/test_batch_save.py
git commit -m "feat(batch): save markdown reports to disk after batch run"
```

---

### Task 5: CLI `batch` Command

**Files:**
- Modify: `cli/main.py`
- Test: `tests/unit/test_batch_cli.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_batch_cli.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/geoffmiles/claude/repos/projects/TradingAgents && .venv/bin/python -m pytest tests/unit/test_batch_cli.py -v`
Expected: FAIL — `batch` command not registered, Typer reports "No such command"

- [ ] **Step 3: Add `batch` command to CLI**

Add the following to `cli/main.py`, after the existing `analyze` command definition (after line ~1290):

```python
@app.command()
def batch(
    tickers: str = typer.Option(..., help="Comma-separated ticker symbols (e.g. AAPL,MSFT,GOOGL)"),
    date: str = typer.Option(
        datetime.date.today().strftime("%Y-%m-%d"),
        help="Trade date in YYYY-MM-DD format",
    ),
    provider: Optional[str] = typer.Option(None, help="LLM provider (openai, anthropic, google, etc.)"),
    deep_model: Optional[str] = typer.Option(None, help="Model for deep analysis"),
    quick_model: Optional[str] = typer.Option(None, help="Model for quick analysis"),
):
    """Run batch analysis across multiple tickers."""
    from tradingagents.batch import BatchRunner

    try:
        datetime.datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        console.print(f"[red]Invalid date format: {date}. Expected YYYY-MM-DD.[/red]")
        raise typer.Exit(1)

    ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    if not ticker_list:
        console.print("[red]No valid tickers provided.[/red]")
        raise typer.Exit(1)

    config = dict(DEFAULT_CONFIG)
    if provider:
        config["llm_provider"] = provider
    if deep_model:
        config["deep_think_llm"] = deep_model
    if quick_model:
        config["quick_think_llm"] = quick_model

    console.print(
        Panel(
            f"[bold]Batch Analysis[/bold]\n"
            f"Tickers: {', '.join(ticker_list)}\n"
            f"Date: {date}\n"
            f"Provider: {config['llm_provider']}",
            title="TradingAgents Batch Mode",
        )
    )

    def on_start(ticker, idx, total):
        console.print(f"\n[bold cyan][{idx + 1}/{total}][/bold cyan] Analyzing {ticker}...")

    def on_done(result):
        if result.error:
            console.print(f"  [red]FAILED:[/red] {result.error}")
        else:
            console.print(f"  [green]Rating:[/green] {result.rating}")

    runner = BatchRunner(config=config)
    results = runner.run(
        ticker_list, date,
        on_ticker_start=on_start,
        on_ticker_done=on_done,
    )

    from tradingagents.batch.report import _extract_decision_summary

    console.print("\n")
    table = Table(title="Batch Results", box=box.ROUNDED)
    table.add_column("Ticker", style="bold")
    table.add_column("Rating")
    table.add_column("Decision")
    table.add_column("Status")

    for r in results.ranked():
        rating_color = {
            "Buy": "green", "Overweight": "green",
            "Hold": "yellow",
            "Underweight": "red", "Sell": "red",
        }.get(r.rating, "white")
        status = f"[red]{r.error}[/red]" if r.error else "[green]OK[/green]"
        decision = _extract_decision_summary(r, max_len=60) if not r.error else "N/A"
        table.add_row(r.ticker, f"[{rating_color}]{r.rating}[/{rating_color}]", decision, status)

    console.print(table)

    save_dir = config.get("batch_save_dir")
    if save_dir:
        console.print(f"\n[dim]Reports saved to {save_dir}/{date}/[/dim]")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/geoffmiles/claude/repos/projects/TradingAgents && .venv/bin/python -m pytest tests/unit/test_batch_cli.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add cli/main.py tests/unit/test_batch_cli.py
git commit -m "feat(batch): add 'batch' CLI command for multi-ticker analysis"
```

---

### Task 6: Final Integration Test and Cleanup

**Files:**
- Modify: `tradingagents/batch/__init__.py` (ensure clean exports)
- Test: `tests/unit/test_batch_integration.py`

- [ ] **Step 1: Write the integration test**

Create `tests/unit/test_batch_integration.py`:

```python
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
```

- [ ] **Step 2: Run integration test**

Run: `cd /Users/geoffmiles/claude/repos/projects/TradingAgents && .venv/bin/python -m pytest tests/unit/test_batch_integration.py -v`
Expected: All 2 tests PASS

- [ ] **Step 3: Run the full test suite to check for regressions**

Run: `cd /Users/geoffmiles/claude/repos/projects/TradingAgents && .venv/bin/python -m pytest tests/ -v`
Expected: All tests PASS (no regressions in existing tests)

- [ ] **Step 4: Commit**

```bash
git add tests/unit/test_batch_integration.py
git commit -m "test(batch): add integration test for full batch pipeline"
```
