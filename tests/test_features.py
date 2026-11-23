from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from valuation_report import load_file, validate_data
from valuation_report.cli import main
from valuation_report.csvio import CsvError, comps_from_csv
from valuation_report.export import results_dict

EX = Path(__file__).resolve().parent.parent / "examples"
SAMPLE = EX / "sample_property.yaml"
COMPS = EX / "comps.csv"
HEADER = "id,address,sale_price,sale_date,gla_sqft,lot_acres,year_built,bedrooms,bathrooms"


def write(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "c.csv"
    p.write_text(text, encoding="utf-8")
    return p


def test_csv_matches_yaml_comps() -> None:
    from_yaml = validate_data(load_file(SAMPLE), EX).report
    data = load_file(SAMPLE)
    data["comparable_sales"] = comps_from_csv(COMPS)
    from_csv = validate_data(data, EX).report
    assert from_yaml is not None and from_csv is not None
    assert from_csv.sales_indication == pytest.approx(from_yaml.sales_indication)
    for a, b in zip(from_yaml.comparable_sales, from_csv.comparable_sales, strict=True):
        assert a.adjusted_price == b.adjusted_price
        assert a.net_adjustment == b.net_adjustment


def test_csv_money_parens_and_blanks(tmp_path: Path) -> None:
    p = write(
        tmp_path,
        HEADER + ",adj:Lot size,adj:Age\n"
        '9,"1 A St","$1,200,500",2026-01-02,1500,0.5,1990,3,2,(2500),\n',
    )
    (comp,) = comps_from_csv(p)
    assert comp["sale_price"] == 1200500
    assert comp["adjustments"] == [{"label": "Lot size", "amount": -2500}]
    assert comp["year_built"] == 1990 and isinstance(comp["year_built"], int)
    assert "weight" not in comp


def test_csv_handles_bom_and_blank_rows(tmp_path: Path) -> None:
    p = tmp_path / "c.csv"
    p.write_bytes(
        b"\xef\xbb\xbf" + (HEADER + "\n1,A,100,2026-01-01,1000,1,2000,2,1\n,,,,,,,,\n").encode()
    )
    assert len(comps_from_csv(p)) == 1


def test_csv_unknown_column(tmp_path: Path) -> None:
    with pytest.raises(CsvError, match="unknown column 'sqft'"):
        comps_from_csv(write(tmp_path, HEADER + ",sqft\n1,A,1,2026-01-01,1,1,2000,1,1,5\n"))


def test_csv_missing_required_column(tmp_path: Path) -> None:
    with pytest.raises(CsvError, match="missing required column 'sale_date'"):
        comps_from_csv(write(tmp_path, "id,address,sale_price\n1,A,100\n"))


def test_csv_bad_number_names_row_and_column(tmp_path: Path) -> None:
    text = HEADER + "\n1,A,100,2026-01-01,1000,1,2000,2,1\n2,B,abc,2026-01-01,1000,1,2000,2,1\n"
    with pytest.raises(CsvError, match=r"row 3, column 'sale_price': 'abc'"):
        comps_from_csv(write(tmp_path, text))


def test_csv_empty_file(tmp_path: Path) -> None:
    with pytest.raises(CsvError, match="empty"):
        comps_from_csv(write(tmp_path, ""))


def test_cli_comps_csv_runs_checks(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bad = write(tmp_path, HEADER + "\n1,A,100000,2026-01-01,1000,1,2000,2,1\n")
    assert main(["validate", str(SAMPLE), "--comps-csv", str(bad)]) == 1
    assert "at least 3 comparable sales" in capsys.readouterr().err


def test_cli_reports_csv_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bad = write(tmp_path, "id,address\n1,A\n")
    assert main(["validate", str(SAMPLE), "--comps-csv", str(bad)]) == 1
    assert "missing required column" in capsys.readouterr().err


def test_cli_json_export(tmp_path: Path) -> None:
    out = tmp_path / "r.json"
    assert main(["build", str(SAMPLE), "--comps-csv", str(COMPS), "--json", str(out)]) == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["opinion_of_value"] == 218000
    assert data["indications"]["cost"] == pytest.approx(211940)
    assert [c["id"] for c in data["comparables"]] == ["1", "2", "3", "4", "5"]
    assert data["comparables"][4]["net_flag"] is True
    assert data["comparables"][0]["net_flag"] is False
    assert "USPAP" in data["disclaimer"]
    assert len(data["warnings"]) == 2


def test_results_dict_rounds_and_lists_weights() -> None:
    rep = validate_data(load_file(SAMPLE), EX).report
    assert rep is not None
    d = results_dict(rep)
    assert d["weights"] == {"sales_comparison": 0.7, "cost": 0.2, "income": 0.1}
    assert d["weighted_value"] == round(rep.weighted_value, 2)
    assert d["warnings"] == []


@pytest.fixture
def data() -> dict[str, Any]:
    loaded = load_file(SAMPLE)
    assert isinstance(loaded, dict)
    return copy.deepcopy(loaded)


def test_spread_warning_when_adjusted_prices_diverge(data: dict[str, Any]) -> None:
    data["comparable_sales"][2]["adjustments"] = [{"label": "Odd", "amount": -40000}]
    data["comparable_sales"][2].pop("stated_adjusted_price")
    res = validate_data(data, EX)
    assert any("adjusted prices span" in w for w in res.warnings)


def test_no_spread_warning_for_sample(data: dict[str, Any]) -> None:
    res = validate_data(data, EX)
    assert not any("adjusted prices span" in w for w in res.warnings)


def test_zero_weight_comp_ignored_in_spread(data: dict[str, Any]) -> None:
    data["comparable_sales"][2]["adjustments"] = [{"label": "Odd", "amount": -40000}]
    data["comparable_sales"][2].pop("stated_adjusted_price")
    data["comparable_sales"][2]["weight"] = 0
    res = validate_data(data, EX)
    assert not any("adjusted prices span" in w for w in res.warnings)
