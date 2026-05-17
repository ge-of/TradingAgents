import pandas as pd
import pytest

from tradingagents.dataflows.structured import (
    AvailabilityStatus,
    DataAvailability,
    FundamentalsSnapshot,
    IndicatorSeries,
    PriceHistory,
)
from tradingagents.dataflows.structured_markdown import (
    format_fundamentals_snapshot_markdown,
    format_indicator_series_markdown,
    format_price_history_markdown,
    format_structured_data_markdown,
)


@pytest.mark.unit
def test_format_fundamentals_snapshot_markdown_matches_report_style_labels():
    snapshot = FundamentalsSnapshot(
        ticker="AAPL",
        as_of="2026-05-16",
        market_cap=3_000_000_000_000,
        pe_ratio_trailing=28.5,
        price_to_book=None,
        dividend_yield=0.006,
        profit_margin=0.252,
        availability=[
            DataAvailability(
                field="price_to_book",
                status=AvailabilityStatus.MISSING,
                message="Provider did not return price_to_book",
                provider="fake_fundamentals",
            )
        ],
    )

    markdown = format_fundamentals_snapshot_markdown(snapshot)

    assert markdown.startswith("# Company Fundamentals for AAPL\n")
    assert "# As of: 2026-05-16" in markdown
    assert "Market Cap: $3,000,000,000,000" in markdown
    assert "PE Ratio (TTM): 28.5" in markdown
    assert "Dividend Yield: 0.6%" in markdown
    assert "Profit Margin: 25.2%" in markdown
    assert "## Data Availability" in markdown
    assert (
        "- price_to_book: missing - Provider did not return price_to_book "
        "(provider: fake_fundamentals)"
    ) in markdown
    assert "None" not in markdown


@pytest.mark.unit
def test_format_price_history_markdown_renders_report_heading_metrics_and_csv():
    history = PriceHistory(
        ticker="AAPL",
        start="2026-05-15",
        end="2026-05-16",
        data=pd.DataFrame(
            {
                "Date": ["2026-05-15", "2026-05-16"],
                "Open": [100.0, 105.0],
                "High": [106.0, 110.0],
                "Low": [99.0, 104.0],
                "Close": [105.0, 108.0],
                "Volume": [1_000_000, 1_100_000],
            }
        ),
        high_52w=110.0,
        low_52w=99.0,
        proximity_to_52w_high=-0.0181818,
    )

    markdown = format_price_history_markdown(history)

    assert markdown.startswith("# Stock data for AAPL from 2026-05-15 to 2026-05-16\n")
    assert "# Total records: 2" in markdown
    assert "52 Week High: 110" in markdown
    assert "52 Week Low: 99" in markdown
    assert "Proximity to 52 Week High: -1.8%" in markdown
    assert "Date,Open,High,Low,Close,Volume" in markdown
    assert "2026-05-15,100.0,106.0,99.0,105.0,1000000" in markdown
    assert "2026-05-16,105.0,110.0,104.0,108.0,1100000" in markdown


@pytest.mark.unit
def test_format_indicator_series_markdown_renders_date_value_lines_and_latest_value():
    series = IndicatorSeries(
        ticker="AAPL",
        indicator="rsi",
        as_of="2026-05-16",
        window=14,
        values=pd.DataFrame(
            {
                "Date": ["2026-05-15", "2026-05-16"],
                "RSI": [62.3, 64.0],
            }
        ),
        latest_value=64.0,
    )

    markdown = format_indicator_series_markdown(series)

    assert markdown.startswith("## RSI values from 2026-05-15 to 2026-05-16:\n")
    assert "2026-05-15: 62.3" in markdown
    assert "2026-05-16: 64.0" in markdown
    assert "Latest RSI: 64.0" in markdown


@pytest.mark.unit
def test_format_structured_data_markdown_dispatches_supported_types():
    snapshot = FundamentalsSnapshot(ticker="MSFT", as_of="2026-05-16", pe_ratio_trailing=30.0)
    history = PriceHistory(
        ticker="MSFT",
        start="2026-05-15",
        end="2026-05-16",
        data=pd.DataFrame({"Date": ["2026-05-16"], "Close": [420.0]}),
    )
    series = IndicatorSeries(
        ticker="MSFT",
        indicator="rsi",
        as_of="2026-05-16",
        window=14,
        values=pd.DataFrame({"Date": ["2026-05-16"], "RSI": [55.0]}),
        latest_value=55.0,
    )

    assert format_structured_data_markdown(snapshot) == format_fundamentals_snapshot_markdown(
        snapshot
    )
    assert format_structured_data_markdown(history) == format_price_history_markdown(history)
    assert format_structured_data_markdown(series) == format_indicator_series_markdown(series)

    with pytest.raises(TypeError, match="Unsupported structured data type for Markdown formatting"):
        format_structured_data_markdown({"ticker": "MSFT"})
