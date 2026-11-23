"""Time the pipeline on the sample and on a larger synthetic report. Prints Markdown.

Run: python scripts/benchmark.py
"""

from __future__ import annotations

import copy
import statistics
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

from valuation_report import load_file, validate_data
from valuation_report.render import render_html, render_pdf

EX = Path(__file__).resolve().parent.parent / "examples"
SAMPLE = EX / "sample_property.yaml"


def timeit(fn: Callable[[], object], runs: int) -> tuple[float, float]:
    """Return (median ms, max ms) over `runs`."""
    times = []
    for _ in range(runs):
        t = time.perf_counter()
        fn()
        times.append((time.perf_counter() - t) * 1000)
    return statistics.median(times), max(times)


def main() -> None:
    data = load_file(SAMPLE)
    big = copy.deepcopy(data)
    base = big["comparable_sales"]
    big["comparable_sales"] = [
        {**copy.deepcopy(base[i % len(base)]), "id": str(i + 1)} for i in range(100)
    ]
    for c in big["comparable_sales"]:
        c.pop("stated_adjusted_price", None)

    def validate_sample() -> None:
        assert validate_data(data, EX).ok

    res = validate_data(data, EX)
    assert res.report is not None
    report = res.report
    big_res = validate_data(big, EX)
    assert big_res.report is not None

    rows = [
        ("validate, sample (5 comps)", *timeit(validate_sample, 200)),
        ("render HTML, sample (5 comps, 2 photos)", *timeit(lambda: render_html(report, EX), 100)),
        ("validate, 100 comps", *timeit(lambda: validate_data(big, EX), 50)),
        (
            "render HTML, 100 comps",
            *timeit(lambda: render_html(big_res.report, EX), 20),  # type: ignore[arg-type]
        ),
    ]
    html = render_html(report, EX)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "r.pdf"
            rows.append(
                (
                    "render PDF, sample (browser launch included)",
                    *timeit(lambda: render_pdf(html, pdf), 5),
                )
            )
            size = pdf.stat().st_size
    except RuntimeError:
        size = 0
    print(f"Python {sys.version.split()[0]}\n")
    print("| Step | Median ms | Max ms |\n|---|---|---|")
    for name, med, mx in rows:
        print(f"| {name} | {med:.1f} | {mx:.1f} |")
    print(f"\nSample HTML size: {len(html.encode()) / 1024:.0f} KB")
    if size:
        print(f"Sample PDF size: {size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
