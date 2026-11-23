"""Machine-readable results, for spreadsheets and other tools."""

from __future__ import annotations

from typing import Any

from .models import Report


def results_dict(r: Report, warnings: list[str] | None = None) -> dict[str, Any]:
    """Computed numbers from a validated report. Dollar values are rounded to cents."""
    t = r.thresholds
    rec = r.reconciliation
    out: dict[str, Any] = {
        "disclaimer": "Not a USPAP appraisal. A USPAP-compliant appraisal requires a licensed "
        "or certified appraiser.",
        "subject_address": r.subject.address,
        "effective_date": r.report.effective_date.isoformat(),
        "opinion_of_value": rec.opinion_of_value,
        "range": [rec.range_low, rec.range_high],
        "weighted_value": round(r.weighted_value, 2),
        "indications": {k: round(v, 2) for k, v in r.indications().items()},
        "weights": dict(rec.weights),
        "comparables": [
            {
                "id": c.id,
                "address": c.address,
                "sale_price": c.sale_price,
                "net_adjustment": round(c.net_adjustment, 2),
                "gross_adjustment": round(c.gross_adjustment, 2),
                "net_pct": round(c.net_pct, 2),
                "gross_pct": round(c.gross_pct, 2),
                "adjusted_price": round(c.adjusted_price, 2),
                "adjusted_per_sqft": round(c.adjusted_per_sqft, 2),
                "weight": c.weight,
                "net_flag": abs(c.net_pct) > t.net_pct,
                "gross_flag": c.gross_pct > t.gross_pct,
            }
            for c in r.comparable_sales
        ],
        "warnings": list(warnings or []),
    }
    return out
