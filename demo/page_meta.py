"""Give the built demo page a real title, description and share preview.

Usage: python demo/page_meta.py SITE_DIR [--meta demo/meta.json]

Reads demo/meta.json ({"title", "description", "url", "image", "repo"}), copies the
screenshot named by "image" into SITE_DIR/demo.png, and rewrites the <head> of
SITE_DIR/index.html: <title>, meta description, Open Graph and Twitter card tags.
Only the head changes, plus a one-line footer link if the page has none. Standard
library only, so any build (Python, Node or a static folder) can call it.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import sys
from pathlib import Path

HOME = "https://chasebuilds.github.io"


def apply(site: Path, meta: dict[str, str], repo_root: Path) -> None:
    page = site / "index.html"
    text = page.read_text(encoding="utf-8")
    if not 140 <= len(meta["description"]) <= 160:
        raise SystemExit(f"description is {len(meta['description'])} chars, want 140 to 160")
    image = repo_root / meta["image"]
    if (site / "demo.png").resolve() != image.resolve():
        shutil.copy2(image, site / "demo.png")
    url = meta["url"].rstrip("/") + "/"
    e = html.escape
    tags = "\n".join(
        [
            f"<title>{e(meta['title'])}</title>",
            f'<meta name="description" content="{e(meta["description"])}">',
            '<meta property="og:type" content="website">',
            f'<meta property="og:title" content="{e(meta["title"])}">',
            f'<meta property="og:description" content="{e(meta["description"])}">',
            f'<meta property="og:url" content="{e(url)}">',
            f'<meta property="og:image" content="{e(url)}demo.png">',
            '<meta name="twitter:card" content="summary_large_image">',
            f'<meta name="twitter:title" content="{e(meta["title"])}">',
            f'<meta name="twitter:description" content="{e(meta["description"])}">',
            f'<meta name="twitter:image" content="{e(url)}demo.png">',
        ]
    )
    # Drop whatever head metadata was there, then put the new block where <title> was.
    old_meta = r'\s*<meta\s+(name|property)="(description|og:[^"]+|twitter:[^"]+)"[^>]*>'
    text = re.sub(old_meta, "", text)
    if re.search(r"<title>.*?</title>", text, flags=re.DOTALL):
        text = re.sub(r"<title>.*?</title>", lambda _: tags, text, count=1, flags=re.DOTALL)
    else:
        text = re.sub(r"(<head[^>]*>)", lambda m: m.group(1) + "\n" + tags, text, count=1)
    if f'href="{HOME}"' not in text and f'href="{HOME}/"' not in text:
        footer = (
            '<p style="text-align:center;font:12px system-ui,sans-serif;opacity:.75;margin:24px 0">'
            f'Built by <a href="{HOME}/">Chase Builds</a> &middot; '
            f'<a href="https://github.com/chasebuilds/{e(meta["repo"])}">Source on GitHub</a></p>'
        )
        if "</body>" in text:
            text = text.replace("</body>", footer + "\n</body>", 1)
        else:
            text += footer
    page.write_text(text, encoding="utf-8", newline="\n")
    print(f"page_meta: {page} -> {meta['title']!r}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("site", type=Path)
    ap.add_argument("--meta", type=Path, default=Path(__file__).resolve().parent / "meta.json")
    a = ap.parse_args()
    meta = json.loads(a.meta.read_text(encoding="utf-8"))
    apply(a.site, meta, a.meta.resolve().parent.parent)
    return 0


if __name__ == "__main__":
    sys.exit(main())
