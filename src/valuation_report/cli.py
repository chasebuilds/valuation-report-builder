"""Command line: validate and render."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .csvio import CsvError, comps_from_csv
from .export import results_dict
from .render import render_html, render_pdf
from .validate import ValidationResult, load_file, validate_data


def _check(path: Path, comps_csv: Path | None = None) -> ValidationResult:
    data = load_file(path)
    if comps_csv is not None:
        if not isinstance(data, dict):
            data = {}
        try:
            data["comparable_sales"] = comps_from_csv(comps_csv)
        except (CsvError, OSError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return ValidationResult(errors=[str(exc)])
    result = validate_data(data, path.parent)
    for w in result.warnings:
        print(f"warning: {w}", file=sys.stderr)
    for e in result.errors:
        print(f"error: {e}", file=sys.stderr)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="valuation-report",
        description="Property valuation report from YAML or JSON. Not a USPAP appraisal.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    csv_help = "replace comparable_sales with rows from this CSV (adjustments as adj:<label>)"
    v = sub.add_parser("validate", help="check an input file")
    v.add_argument("input", type=Path)
    v.add_argument("--comps-csv", type=Path, help=csv_help)
    b = sub.add_parser("build", help="render HTML, PDF and/or JSON results")
    b.add_argument("input", type=Path)
    b.add_argument("--comps-csv", type=Path, help=csv_help)
    b.add_argument("--json", type=Path, help="write computed results as JSON here")
    b.add_argument("--html", type=Path, help="write HTML here")
    b.add_argument("--pdf", type=Path, help="write PDF here")
    b.add_argument("--browser", help="Playwright channel, e.g. msedge or chrome")
    args = parser.parse_args(argv)

    result = _check(args.input, args.comps_csv)
    if not result.ok or result.report is None:
        print(f"{len(result.errors)} error(s). Nothing written.", file=sys.stderr)
        return 1
    if args.cmd == "validate":
        print(f"OK: {len(result.warnings)} warning(s)")
        return 0
    if not (args.html or args.pdf or args.json):
        parser.error("give --html, --pdf and/or --json")
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(results_dict(result.report, result.warnings), indent=2) + chr(10),
            encoding="utf-8",
            newline=chr(10),
        )
        print(f"wrote {args.json}")
    html = render_html(result.report, args.input.parent, result.warnings)
    if args.html:
        args.html.parent.mkdir(parents=True, exist_ok=True)
        args.html.write_text(html, encoding="utf-8", newline="\n")
        print(f"wrote {args.html}")
    if args.pdf:
        render_pdf(html, args.pdf, args.browser)
        print(f"wrote {args.pdf}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
