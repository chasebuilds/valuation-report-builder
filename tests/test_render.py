from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

import pytest

from valuation_report import load_file, validate_data
from valuation_report.cli import main
from valuation_report.render import render_html, render_pdf

ROOT = Path(__file__).resolve().parent.parent
EX = ROOT / "examples"
SAMPLE = EX / "sample_property.yaml"
GOLDEN = Path(__file__).parent / "golden" / "sample.html"


def sample_html() -> str:
    res = validate_data(load_file(SAMPLE), EX)
    assert res.report is not None
    return render_html(res.report, EX, res.warnings)


def test_html_matches_golden() -> None:
    html = sample_html()
    if os.environ.get("UPDATE_GOLDEN"):
        GOLDEN.parent.mkdir(exist_ok=True)
        GOLDEN.write_text(html, encoding="utf-8", newline="\n")
    assert html == GOLDEN.read_text(encoding="utf-8")


def test_html_has_disclaimer_and_sections() -> None:
    html = sample_html()
    assert "NOT an appraisal" in html
    assert "USPAP-compliant appraisal requires a licensed or certified appraiser" in html
    for anchor in ("subject", "sales", "cost", "income", "reconciliation", "scope"):
        assert f'id="{anchor}"' in html
    assert "Map placeholder" in html
    assert html.count("data:image/svg+xml;base64,") == 2


def test_html_is_deterministic_and_self_contained() -> None:
    assert sample_html() == sample_html()
    assert not re.search(r'(src|href)="https?://', sample_html())


def test_no_em_dash_in_output() -> None:
    assert "—" not in sample_html()


def test_html_escapes_input() -> None:
    d = load_file(SAMPLE)
    d["subject"]["address"] = "<script>alert(1)</script>"
    res = validate_data(d, EX)
    assert res.report is not None
    html = render_html(res.report, EX)
    assert "<script>alert" not in html
    assert "&lt;script&gt;" in html


def test_cli_validate_and_build_html(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["validate", str(SAMPLE)]) == 0
    out = tmp_path / "r.html"
    assert main(["build", str(SAMPLE), "--html", str(out)]) == 0
    assert out.read_text(encoding="utf-8") == sample_html()
    capsys.readouterr()


def test_cli_refuses_bad_input(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("report: {}\n", encoding="utf-8")
    out = tmp_path / "r.html"
    assert main(["build", str(bad), "--html", str(out)]) == 1
    assert not out.exists()
    assert "error:" in capsys.readouterr().err


@pytest.mark.pdf
def test_pdf_renders(tmp_path: Path) -> None:
    out = tmp_path / "r.pdf"
    try:
        render_pdf(sample_html(), out)
    except RuntimeError:
        if shutil.which("playwright") is None:
            pytest.skip("no Chromium available")
        raise
    data = out.read_bytes()
    assert data.startswith(b"%PDF")
    assert len(data) > 20_000
