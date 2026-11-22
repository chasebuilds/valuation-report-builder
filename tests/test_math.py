from __future__ import annotations

from pathlib import Path

import pytest

from valuation_report import Report, load_file, validate_data
from valuation_report.render import usd

SAMPLE = Path(__file__).resolve().parent.parent / "examples" / "sample_property.yaml"


@pytest.fixture
def report() -> Report:
    res = validate_data(load_file(SAMPLE), SAMPLE.parent)
    assert res.report is not None
    return res.report


def test_comp_adjustments(report: Report) -> None:
    c = report.comparable_sales[1]
    assert c.net_adjustment == -10000
    assert c.gross_adjustment == 14000
    assert c.adjusted_price == 226500
    assert c.net_pct == pytest.approx(-4.228, abs=0.001)
    assert c.gross_pct == pytest.approx(5.919, abs=0.001)


def test_weighted_sales_indication(report: Report) -> None:
    prices = [219000, 226500, 211300, 227500, 221500]
    weights = [1, 1, 1, 1, 0.5]
    expected = sum(p * w for p, w in zip(prices, weights, strict=True)) / sum(weights)
    assert report.sales_indication == pytest.approx(expected)


def test_cost_approach(report: Report) -> None:
    c = report.cost_approach
    assert c is not None
    assert c.replacement_cost_new == 1640 * 118 + 440 * 42 + 11000
    assert c.physical_depreciation == pytest.approx(c.replacement_cost_new * 0.22)
    assert c.indicated_value == pytest.approx(211940)


def test_income_approach(report: Report) -> None:
    i = report.income_approach
    assert i is not None
    assert i.indicated_value == 1350 * 155
    assert i.grm_low < i.selected_grm < i.grm_high


def test_weighted_value(report: Report) -> None:
    ind = report.indications()
    expected = ind["sales_comparison"] * 0.7 + ind["cost"] * 0.2 + ind["income"] * 0.1
    assert report.weighted_value == pytest.approx(expected)


def test_usd_format() -> None:
    assert usd(1234567) == "$1,234,567"
    assert usd(-500) == "-$500"
    assert usd(500, signed=True) == "+$500"
    assert usd(0, signed=True) == "$0"
