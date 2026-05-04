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
