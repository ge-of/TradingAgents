from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from tradingagents.agents.utils.rating import RATINGS_5_TIER

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
