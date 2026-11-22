"""Load input files and check them. Errors block a report; warnings print in it."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from .models import Report

MIN_COMPS = 3
MONEY_TOLERANCE = 1.0
WEIGHT_TOLERANCE = 0.001
STALE_SALE_DAYS = 365
OPINION_DRIFT_PCT = 3.0
ROUNDING_SLACK = 0.01  # an opinion may be rounded up to 1% past the indications


@dataclass
class ValidationResult:
    report: Report | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors and self.report is not None


def load_file(path: Path) -> Any:
    """Read YAML or JSON by file extension."""
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        return json.loads(text)
    return yaml.safe_load(text)


def _loc(parts: tuple[int | str, ...]) -> str:
    return ".".join(str(p) for p in parts) or "(root)"


def _money(x: float) -> str:
    return f"${x:,.0f}"


def validate_data(data: object, base_dir: Path | None = None) -> ValidationResult:
    """Validate raw input. `base_dir` is where photo paths are resolved."""
    result = ValidationResult()
    if not isinstance(data, dict):
        result.errors.append("(root): input must be a mapping of sections, got something else")
        return result
    comps_raw = data.get("comparable_sales")
    if isinstance(comps_raw, list) and len(comps_raw) < MIN_COMPS:
        result.errors.append(
            f"comparable_sales: at least {MIN_COMPS} comparable sales are required, "
            f"found {len(comps_raw)}"
        )
    try:
        report = Report.model_validate(data)
    except ValidationError as exc:
        for err in exc.errors():
            result.errors.append(f"{_loc(err['loc'])}: {err['msg']}")
        return result
    result.report = report
    _check_comps(report, result)
    _check_cost(report, result)
    _check_income(report, result)
    _check_reconciliation(report, result)
    _check_photos(report, result, base_dir)
    if result.errors:
        result.report = None
    return result


def _check_comps(r: Report, out: ValidationResult) -> None:
    seen: set[str] = set()
    for i, c in enumerate(r.comparable_sales):
        where = f"comparable_sales.{i} ({c.id})"
        if c.id in seen:
            out.errors.append(f"{where}: duplicate comp id '{c.id}'")
        seen.add(c.id)
        if c.sale_date > r.report.effective_date:
            out.errors.append(
                f"{where}: sale date {c.sale_date} is after the effective date "
                f"{r.report.effective_date}"
            )
        elif (r.report.effective_date - c.sale_date).days > STALE_SALE_DAYS:
            out.warnings.append(f"{where}: sale is more than 12 months before the effective date")
        if c.stated_adjusted_price is not None and (
            abs(c.stated_adjusted_price - c.adjusted_price) > MONEY_TOLERANCE
        ):
            out.errors.append(
                f"{where}: adjustments do not sum. Sale price {_money(c.sale_price)} plus "
                f"adjustments {_money(c.net_adjustment)} is {_money(c.adjusted_price)}, "
                f"but stated adjusted price is {_money(c.stated_adjusted_price)}"
            )
        if c.net_pct > r.thresholds.net_pct or -c.net_pct > r.thresholds.net_pct:
            out.warnings.append(
                f"{where}: net adjustment {c.net_pct:+.1f}% is over the "
                f"{r.thresholds.net_pct:.0f}% flag level"
            )
        if c.gross_pct > r.thresholds.gross_pct:
            out.warnings.append(
                f"{where}: gross adjustment {c.gross_pct:.1f}% is over the "
                f"{r.thresholds.gross_pct:.0f}% flag level"
            )
    if all(c.weight == 0 for c in r.comparable_sales):
        out.errors.append("comparable_sales: at least one comp needs a weight above 0")


def _check_cost(r: Report, out: ValidationResult) -> None:
    c = r.cost_approach
    if c is None:
        return
    if c.stated_indicated_value is not None and (
        abs(c.stated_indicated_value - c.indicated_value) > MONEY_TOLERANCE
    ):
        out.errors.append(
            f"cost_approach: land plus depreciated improvements is {_money(c.indicated_value)}, "
            f"but stated indicated value is {_money(c.stated_indicated_value)}"
        )
    if c.total_depreciation > c.replacement_cost_new:
        out.errors.append("cost_approach: total depreciation is larger than replacement cost new")


def _check_income(r: Report, out: ValidationResult) -> None:
    inc = r.income_approach
    if inc is None:
        return
    if len(inc.rent_comps) < MIN_COMPS:
        out.errors.append(
            f"income_approach.rent_comps: at least {MIN_COMPS} rental comps are required, "
            f"found {len(inc.rent_comps)}"
        )
        return
    if not inc.grm_low <= inc.selected_grm <= inc.grm_high:
        out.errors.append(
            f"income_approach: selected GRM {inc.selected_grm:.1f} is outside the comp range "
            f"{inc.grm_low:.1f} to {inc.grm_high:.1f}"
        )
    if inc.stated_indicated_value is not None and (
        abs(inc.stated_indicated_value - inc.indicated_value) > MONEY_TOLERANCE
    ):
        out.errors.append(
            f"income_approach: rent times GRM is {_money(inc.indicated_value)}, but stated "
            f"indicated value is {_money(inc.stated_indicated_value)}"
        )


def _check_reconciliation(r: Report, out: ValidationResult) -> None:
    rec = r.reconciliation
    if all(c.weight == 0 for c in r.comparable_sales):
        return
    ind = r.indications()
    for key in rec.weights:
        if key not in ind:
            out.errors.append(
                f"reconciliation.weights.{key}: weight given but no {key} approach in the input"
            )
    for name in ind:
        if name not in rec.weights:
            out.errors.append(f"reconciliation.weights.{name}: missing, the approach is included")
    if out.errors and any(e.startswith("reconciliation.weights") for e in out.errors):
        return
    total = sum(rec.weights.values())
    if abs(total - 1.0) > WEIGHT_TOLERANCE:
        out.errors.append(f"reconciliation.weights: weights sum to {total:.3f}, must sum to 1")
        return
    lo, hi = min(ind.values()), max(ind.values())
    slack = hi * ROUNDING_SLACK
    if not lo - slack <= rec.opinion_of_value <= hi + slack:
        out.errors.append(
            f"reconciliation.opinion_of_value: {_money(rec.opinion_of_value)} is outside the "
            f"indications {_money(lo)} to {_money(hi)}"
        )
    drift = abs(rec.opinion_of_value - r.weighted_value) / r.weighted_value * 100
    if drift > OPINION_DRIFT_PCT:
        out.warnings.append(
            f"reconciliation: stated opinion differs from the weighted value "
            f"{_money(r.weighted_value)} by {drift:.1f}%"
        )
    if rec.range_low is not None and rec.range_high is not None:
        if rec.range_low > rec.range_high:
            out.errors.append("reconciliation: range_low is above range_high")
        elif not rec.range_low <= rec.opinion_of_value <= rec.range_high:
            out.errors.append("reconciliation: opinion_of_value is outside the stated range")
    elif (rec.range_low is None) != (rec.range_high is None):
        out.errors.append("reconciliation: give both range_low and range_high, or neither")


def _check_photos(r: Report, out: ValidationResult, base_dir: Path | None) -> None:
    base = base_dir or Path.cwd()
    paths = [(f"photos.{i}.path", p.path) for i, p in enumerate(r.photos)]
    if r.map_image:
        paths.append(("map_image", r.map_image))
    for where, rel in paths:
        if not (base / rel).is_file():
            out.errors.append(f"{where}: file not found: {rel}")
