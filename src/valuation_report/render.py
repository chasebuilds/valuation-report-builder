"""Render a validated report to HTML and PDF."""

from __future__ import annotations

import base64
import mimetypes
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jinja2 import Environment, PackageLoader, select_autoescape
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

from .models import Report

DISCLAIMER = (
    "This is an analysis and education product. It is NOT an appraisal and was NOT prepared "
    "under USPAP. A USPAP-compliant appraisal requires a licensed or certified appraiser."
)
FOOTER_TEXT = (
    "Not a USPAP appraisal. A USPAP-compliant appraisal requires a licensed or certified appraiser."
)


def usd(x: float, signed: bool = False) -> str:
    sign = "+" if signed and x > 0 else ""
    if x < 0:
        return f"-${abs(x):,.0f}"
    return f"{sign}${x:,.0f}"


def num(x: float, places: int = 0) -> str:
    return f"{x:,.{places}f}"


def _data_uri(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


@dataclass
class GridRow:
    label: str
    subject: str
    values: list[str]
    kind: str = "plain"  # plain | adjustment | total | flag
    flags: list[bool] | None = None


def build_grid(r: Report) -> list[GridRow]:
    s, comps = r.subject, r.comparable_sales
    rows = [
        GridRow("Address", s.address, [c.address for c in comps]),
        GridRow("Proximity to subject", "", [c.proximity or "n/a" for c in comps]),
        GridRow("Data source", "", [c.data_source or "n/a" for c in comps]),
        GridRow("Sale price", "", [usd(c.sale_price) for c in comps]),
        GridRow("Sale date", "", [c.sale_date.isoformat() for c in comps]),
        GridRow("Gross living area (sq ft)", num(s.gla_sqft), [num(c.gla_sqft) for c in comps]),
        GridRow("Price per sq ft", "", [usd(c.price_per_sqft) for c in comps]),
        GridRow("Lot (acres)", num(s.lot_acres, 2), [num(c.lot_acres, 2) for c in comps]),
        GridRow("Year built", str(s.year_built), [str(c.year_built) for c in comps]),
        GridRow("Condition", s.condition, [c.condition or "n/a" for c in comps]),
        GridRow(
            "Bedrooms / baths",
            f"{s.bedrooms} / {s.bathrooms:g}",
            [f"{c.bedrooms} / {c.bathrooms:g}" for c in comps],
        ),
        GridRow("Garage", s.garage, [c.garage for c in comps]),
    ]
    labels: list[str] = []
    for c in comps:
        for a in c.adjustments:
            if a.label not in labels:
                labels.append(a.label)
    for label in labels:
        vals = []
        for c in comps:
            amt = sum(a.amount for a in c.adjustments if a.label == label)
            has = any(a.label == label for a in c.adjustments)
            vals.append(usd(amt, signed=True) if has else "-")
        rows.append(GridRow(f"Adj: {label}", "", vals, kind="adjustment"))
    t = r.thresholds
    rows += [
        GridRow("Net adjustment", "", [usd(c.net_adjustment, True) for c in comps], "total"),
        GridRow(
            "Net adjustment %",
            "",
            [f"{c.net_pct:+.1f}%" for c in comps],
            "flag",
            [abs(c.net_pct) > t.net_pct for c in comps],
        ),
        GridRow(
            "Gross adjustment %",
            "",
            [f"{c.gross_pct:.1f}%" for c in comps],
            "flag",
            [c.gross_pct > t.gross_pct for c in comps],
        ),
        GridRow("Adjusted price", "", [usd(c.adjusted_price) for c in comps], "total"),
        GridRow("Adjusted price per sq ft", "", [usd(c.adjusted_per_sqft) for c in comps]),
        GridRow("Weight in indication", "", [f"{c.weight:g}" for c in comps]),
    ]
    return rows


def render_html(r: Report, base_dir: Path | None = None, warnings: list[str] | None = None) -> str:
    base = base_dir or Path.cwd()
    env = Environment(
        loader=PackageLoader("valuation_report", "templates"),
        autoescape=select_autoescape(["html", "j2"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["usd"] = usd
    env.filters["num"] = num
    photos = [{"uri": _data_uri(base / p.path), "caption": p.caption} for p in r.photos]
    ctx: dict[str, Any] = {
        "r": r,
        "grid": build_grid(r),
        "photos": photos,
        "map_uri": _data_uri(base / r.map_image) if r.map_image else None,
        "disclaimer": DISCLAIMER,
        "warnings": warnings or [],
        "indications": r.indications(),
        "approach_names": {
            "sales_comparison": "Sales comparison",
            "cost": "Cost",
            "income": "Income (GRM)",
        },
    }
    return env.get_template("report.html.j2").render(**ctx)


def _footer_html() -> str:
    return (
        '<div style="width:100%;font-size:7.5px;color:#555;padding:0 14mm;'
        'display:flex;justify-content:space-between;font-family:Arial,sans-serif">'
        f"<span>{FOOTER_TEXT}</span>"
        '<span>Page <span class="pageNumber"></span> of <span class="totalPages"></span></span>'
        "</div>"
    )


def render_pdf(html: str, out_path: Path, channel: str | None = None) -> None:
    """Print HTML to PDF with Chromium through Playwright.

    Tries `channel` (or env VRB_BROWSER_CHANNEL), then Playwright's bundled Chromium,
    then installed Edge and Chrome.
    """
    wanted = channel or os.environ.get("VRB_BROWSER_CHANNEL")
    attempts: list[str | None] = [wanted] if wanted else [None, "msedge", "chrome"]
    last: Exception | None = None
    with sync_playwright() as p:
        for ch in attempts:
            try:
                browser = p.chromium.launch(channel=ch) if ch else p.chromium.launch()
            except PlaywrightError as exc:
                last = exc
                continue
            try:
                page = browser.new_page()
                page.set_content(html, wait_until="load")
                out_path.parent.mkdir(parents=True, exist_ok=True)
                page.pdf(
                    path=str(out_path),
                    format="Letter",
                    print_background=True,
                    display_header_footer=True,
                    header_template="<div></div>",
                    footer_template=_footer_html(),
                    margin={"top": "14mm", "bottom": "16mm", "left": "14mm", "right": "14mm"},
                )
            finally:
                browser.close()
            return
    raise RuntimeError(
        "No Chromium browser found. Run `playwright install chromium` or install Edge/Chrome."
    ) from last
