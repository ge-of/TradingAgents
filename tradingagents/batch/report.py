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
