"""Command line: validate and render."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .render import render_html, render_pdf
from .validate import ValidationResult, load_file, validate_data


def _check(path: Path) -> ValidationResult:
    result = validate_data(load_file(path), path.parent)
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
    v = sub.add_parser("validate", help="check an input file")
    v.add_argument("input", type=Path)
    b = sub.add_parser("build", help="render HTML and/or PDF")
    b.add_argument("input", type=Path)
    b.add_argument("--html", type=Path, help="write HTML here")
    b.add_argument("--pdf", type=Path, help="write PDF here")
    b.add_argument("--browser", help="Playwright channel, e.g. msedge or chrome")
    args = parser.parse_args(argv)

    result = _check(args.input)
    if not result.ok or result.report is None:
        print(f"{len(result.errors)} error(s). Nothing written.", file=sys.stderr)
        return 1
    if args.cmd == "validate":
        print(f"OK: {len(result.warnings)} warning(s)")
        return 0
    if not args.html and not args.pdf:
        parser.error("give --html and/or --pdf")
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
