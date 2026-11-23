"""Read comparable sales from a spreadsheet export (CSV).

One row per comp. Plain columns match the comparable_sales fields. Adjustments are
columns named `adj:<label>`, for example `adj:Living area`. Money may be written as
`$214,000`. Empty cells are left out so the schema defaults apply.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

NUMERIC = {
    "sale_price",
    "gla_sqft",
    "lot_acres",
    "year_built",
    "bedrooms",
    "bathrooms",
    "weight",
    "stated_adjusted_price",
}
KNOWN = NUMERIC | {
    "id",
    "address",
    "proximity",
    "sale_date",
    "data_source",
    "condition",
    "garage",
}
ADJ_PREFIX = "adj:"


class CsvError(ValueError):
    """Bad CSV layout or cell. The message names the row and column."""


def _number(text: str) -> float:
    cleaned = text.replace("$", "").replace(",", "").strip()
    neg = cleaned.startswith("(") and cleaned.endswith(")")
    value = float(cleaned.strip("()"))
    return -value if neg else value


def comps_from_csv(path: Path) -> list[dict[str, Any]]:
    """Return comparable_sales dicts, ready for validation."""
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        headers = [h.strip() for h in (reader.fieldnames or [])]
        if not headers:
            raise CsvError(f"{path.name}: file is empty or has no header row")
        for h in headers:
            if h not in KNOWN and not h.startswith(ADJ_PREFIX):
                raise CsvError(
                    f"{path.name}: unknown column '{h}'. Use the comparable_sales field "
                    f"names or 'adj:<label>' for adjustments"
                )
        for need in ("id", "address", "sale_price", "sale_date"):
            if need not in headers:
                raise CsvError(f"{path.name}: missing required column '{need}'")
        comps: list[dict[str, Any]] = []
        for line_no, raw in enumerate(reader, start=2):
            row = {k.strip(): (v or "").strip() for k, v in raw.items() if k is not None}
            if not any(row.values()):
                continue
            comp: dict[str, Any] = {}
            adjustments: list[dict[str, Any]] = []
            for col, text in row.items():
                if text == "":
                    continue
                try:
                    if col.startswith(ADJ_PREFIX):
                        adjustments.append(
                            {"label": col[len(ADJ_PREFIX) :], "amount": _number(text)}
                        )
                    elif col in NUMERIC:
                        comp[col] = (
                            int(_number(text))
                            if col in {"year_built", "bedrooms"}
                            else _number(text)
                        )
                    else:
                        comp[col] = text
                except ValueError as exc:
                    raise CsvError(
                        f"{path.name} row {line_no}, column '{col}': '{text}' is not a number"
                    ) from exc
            comp["adjustments"] = adjustments
            comps.append(comp)
    return comps
