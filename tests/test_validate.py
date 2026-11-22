from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

from valuation_report import load_file, validate_data

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "examples" / "sample_property.yaml"


@pytest.fixture
def data() -> dict[str, Any]:
    loaded = load_file(SAMPLE)
    assert isinstance(loaded, dict)
    return copy.deepcopy(loaded)


def run(d: dict[str, Any]) -> tuple[list[str], list[str]]:
    res = validate_data(d, SAMPLE.parent)
    return res.errors, res.warnings


def test_sample_is_valid_with_two_flags(data: dict[str, Any]) -> None:
    res = validate_data(data, SAMPLE.parent)
    assert res.ok
    assert len(res.warnings) == 2
    assert all("comparable_sales.4" in w for w in res.warnings)


def test_non_mapping_input() -> None:
    errors, _ = run([1, 2])  # type: ignore[arg-type]
    assert errors and "mapping" in errors[0]


def test_missing_section_is_named(data: dict[str, Any]) -> None:
    del data["site"]
    errors, _ = run(data)
    assert any(e.startswith("site:") for e in errors)


def test_unknown_field_rejected(data: dict[str, Any]) -> None:
    data["subject"]["sqft"] = 10
    errors, _ = run(data)
    assert any("subject.sqft" in e for e in errors)


def test_too_few_comps(data: dict[str, Any]) -> None:
    data["comparable_sales"] = data["comparable_sales"][:2]
    errors, _ = run(data)
    assert any("at least 3 comparable sales" in e and "found 2" in e for e in errors)


def test_adjustments_do_not_sum(data: dict[str, Any]) -> None:
    data["comparable_sales"][0]["stated_adjusted_price"] = 230000
    errors, _ = run(data)
    assert any("adjustments do not sum" in e and "$219,000" in e for e in errors)


def test_rounding_tolerance_allows_one_dollar(data: dict[str, Any]) -> None:
    data["comparable_sales"][0]["stated_adjusted_price"] = 219000.5
    errors, _ = run(data)
    assert not errors


def test_net_and_gross_flags_follow_thresholds(data: dict[str, Any]) -> None:
    data["thresholds"] = {"net_pct": 1, "gross_pct": 2}
    _, warnings = run(data)
    assert any("net adjustment" in w and "1%" in w for w in warnings)
    assert any("gross adjustment" in w and "2%" in w for w in warnings)


def test_negative_net_adjustment_is_flagged(data: dict[str, Any]) -> None:
    data["comparable_sales"][1]["adjustments"] = [{"label": "Big", "amount": -50000}]
    data["comparable_sales"][1].pop("stated_adjusted_price")
    _, warnings = run(data)
    assert any("comparable_sales.1" in w and "net adjustment" in w for w in warnings)


def test_duplicate_comp_id(data: dict[str, Any]) -> None:
    data["comparable_sales"][1]["id"] = "1"
    errors, _ = run(data)
    assert any("duplicate comp id" in e for e in errors)


def test_sale_after_effective_date(data: dict[str, Any]) -> None:
    data["comparable_sales"][0]["sale_date"] = "2026-12-01"
    errors, _ = run(data)
    assert any("after the effective date" in e for e in errors)


def test_old_sale_warns(data: dict[str, Any]) -> None:
    data["comparable_sales"][3]["sale_date"] = "2025-01-01"
    _, warnings = run(data)
    assert any("more than 12 months" in w for w in warnings)


def test_cost_stated_value_mismatch(data: dict[str, Any]) -> None:
    data["cost_approach"]["stated_indicated_value"] = 300000
    errors, _ = run(data)
    assert any(e.startswith("cost_approach:") and "$211,940" in e for e in errors)


def test_grm_outside_range(data: dict[str, Any]) -> None:
    data["income_approach"]["selected_grm"] = 300
    errors, _ = run(data)
    assert any("outside the comp range" in e for e in errors)


def test_income_needs_three_rent_comps(data: dict[str, Any]) -> None:
    data["income_approach"]["rent_comps"] = data["income_approach"]["rent_comps"][:2]
    errors, _ = run(data)
    assert any("rental comps are required" in e for e in errors)


def test_weights_must_sum_to_one(data: dict[str, Any]) -> None:
    data["reconciliation"]["weights"]["cost"] = 0.4
    errors, _ = run(data)
    assert any("must sum to 1" in e for e in errors)


def test_weight_for_missing_approach(data: dict[str, Any]) -> None:
    del data["income_approach"]
    errors, _ = run(data)
    assert any("reconciliation.weights.income" in e for e in errors)


def test_missing_weight_for_included_approach(data: dict[str, Any]) -> None:
    del data["reconciliation"]["weights"]["income"]
    errors, _ = run(data)
    assert any("weights.income: missing" in e for e in errors)


def test_optional_approaches_can_be_dropped(data: dict[str, Any]) -> None:
    del data["income_approach"], data["cost_approach"]
    data["reconciliation"]["weights"] = {"sales_comparison": 1.0}
    data["reconciliation"]["opinion_of_value"] = 221000
    res = validate_data(data, SAMPLE.parent)
    assert res.ok, res.errors


def test_opinion_outside_indications(data: dict[str, Any]) -> None:
    data["reconciliation"]["opinion_of_value"] = 260000
    data["reconciliation"]["range_high"] = 270000
    errors, _ = run(data)
    assert any("outside the indications" in e for e in errors)


def test_opinion_drift_warns(data: dict[str, Any]) -> None:
    data["reconciliation"]["opinion_of_value"] = 225000
    data["reconciliation"]["range_high"] = 230000
    _, warnings = run(data)
    assert any("differs from the weighted value" in w for w in warnings)


def test_range_must_hold_opinion(data: dict[str, Any]) -> None:
    data["reconciliation"]["range_low"] = 219000
    errors, _ = run(data)
    assert any("outside the stated range" in e for e in errors)


def test_range_needs_both_ends(data: dict[str, Any]) -> None:
    del data["reconciliation"]["range_high"]
    errors, _ = run(data)
    assert any("both range_low and range_high" in e for e in errors)


def test_missing_photo_file(data: dict[str, Any]) -> None:
    data["photos"][0]["path"] = "photos/nope.jpg"
    errors, _ = run(data)
    assert any("photos.0.path: file not found" in e for e in errors)


def test_zero_weights_rejected(data: dict[str, Any]) -> None:
    for c in data["comparable_sales"]:
        c["weight"] = 0
    errors, _ = run(data)
    assert any("weight above 0" in e for e in errors)


def test_json_loads(tmp_path: Path, data: dict[str, Any]) -> None:
    import json

    p = tmp_path / "in.json"
    p.write_text(json.dumps(data, default=str), encoding="utf-8")
    assert validate_data(load_file(p), SAMPLE.parent).ok
