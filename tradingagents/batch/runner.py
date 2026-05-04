from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from tradingagents.agents.utils.rating import RATINGS_5_TIER
from tradingagents.batch.report import generate_summary_report, generate_ticker_report
from tradingagents.dataflows.utils import safe_ticker_component
from tradingagents.graph.trading_graph import TradingAgentsGraph

logger = logging.getLogger(__name__)


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


class BatchRunner:
    def __init__(self, config=None, graph=None):
        from tradingagents.default_config import DEFAULT_CONFIG

        self.config = config or DEFAULT_CONFIG.copy()
        if graph is not None:
            self.graph = graph
        else:
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
