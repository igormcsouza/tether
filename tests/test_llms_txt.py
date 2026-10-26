"""llms.txt lists every page of the site with its URL (#64)."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
LLMS = (DOCS / "llms.txt").read_text()
BASE = "https://igormcsouza.github.io/tether/"


def _url(page: Path) -> str:
    rel = page.relative_to(DOCS).with_suffix("")
    return BASE if rel.name == "index" and len(rel.parts) == 1 else f"{BASE}{rel}/"


def test_every_page_is_listed() -> None:
    missing = []
    for p in DOCS.rglob("*.md"):
        url = _url(p).replace("/index/", "/")
        if url not in LLMS:
            missing.append(str(p.relative_to(DOCS)))
    assert not missing, f"not in llms.txt: {missing}"


def test_follows_the_llms_txt_shape() -> None:
    lines = LLMS.splitlines()
    assert lines[0] == "# tether" and lines[2].startswith("> ")
    assert all(re.match(r"- \[.+\]\(https?://\S+\)", x) for x in lines if x.startswith("- "))
