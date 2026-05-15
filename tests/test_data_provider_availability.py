import pandas as pd
import pytest

from tradingagents.dataflows.availability import (
    ProviderResultRole,
    is_empty_provider_result,
    normalize_provider_result,
)
from tradingagents.dataflows.exceptions import ProviderNoDataError


@pytest.mark.unit
@pytest.mark.parametrize(
    "result",
    [
        None,
        "",
        [],
        {},
        pd.DataFrame(),
    ],
)
def test_empty_provider_results_are_classified_as_no_top_level_data(result):
    assert is_empty_provider_result(result) is True


@pytest.mark.unit
@pytest.mark.parametrize(
    "result",
    [
        "No data found for symbol 'AAPL'",
        [None],
        {"pe_ratio": None},
        pd.DataFrame({"close": [101.25]}),
    ],
)
def test_non_empty_provider_results_preserve_partial_or_report_data(result):
    assert is_empty_provider_result(result) is False


@pytest.mark.unit
def test_required_empty_provider_result_raises_no_data_error():
    with pytest.raises(ProviderNoDataError) as exc_info:
        normalize_provider_result(
            pd.DataFrame(),
            provider="yfinance",
            method="get_stock_data",
            role=ProviderResultRole.REQUIRED,
            no_data_message="No price bars found for AAPL from 2026-05-01 to 2026-05-02",
            details={
                "ticker": "AAPL",
                "start_date": "2026-05-01",
                "end_date": "2026-05-02",
            },
        )

    error = exc_info.value
    assert error.provider == "yfinance"
    assert error.method == "get_stock_data"
    assert error.retryable is False
    assert error.details == {
        "ticker": "AAPL",
        "start_date": "2026-05-01",
        "end_date": "2026-05-02",
    }
    assert error.message == "No price bars found for AAPL from 2026-05-01 to 2026-05-02"


@pytest.mark.unit
def test_optional_empty_provider_result_is_returned_unchanged():
    result = []

    returned = normalize_provider_result(
        result,
        provider="yfinance",
        method="get_news",
        role=ProviderResultRole.OPTIONAL,
        no_data_message="No news articles found for AAPL",
        details={"ticker": "AAPL"},
    )

    assert returned is result


@pytest.mark.unit
def test_required_non_empty_provider_result_is_returned_unchanged():
    result = pd.DataFrame({"Date": ["2026-05-01"], "Close": [101.25]})

    returned = normalize_provider_result(
        result,
        provider="alpha_vantage",
        method="get_stock_data",
        role=ProviderResultRole.REQUIRED,
        no_data_message="No price bars found",
    )

    assert returned is result
