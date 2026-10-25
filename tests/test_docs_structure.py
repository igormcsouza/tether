"""Every docs page is in the nav and says who it is for and what it enables (#151)."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
NAV = (ROOT / "mkdocs.yml").read_text().split("nav:", 1)[1]
SKIP = {"release-notes.md"}  # a changelog, not a guide


def _pages() -> list[Path]:
    return sorted(p for p in DOCS.rglob("*.md") if p.name not in SKIP)


def test_every_page_is_in_the_nav() -> None:
    listed = set(re.findall(r"([\w/-]+\.md)", NAV))
    missing = [str(p.relative_to(DOCS)) for p in _pages() if str(p.relative_to(DOCS)) not in listed]
    assert not missing, f"not in nav: {missing}"


def test_every_nav_entry_exists() -> None:
    for name in re.findall(r"([\w/-]+\.md)", NAV):
        assert (DOCS / name).is_file(), name


def test_every_page_opens_with_who_it_is_for() -> None:
    bad = []
    for p in _pages():
        body = [x for x in p.read_text().splitlines() if x.strip()]
        if p.relative_to(DOCS).parts[0] == "reference" and p.name not in {
            "index.md",
            "cli.md",
            "agent-interface.md",
        }:
            continue  # API pages generated from docstrings
        if not body[1].startswith("*For:"):
            bad.append(str(p.relative_to(DOCS)))
    assert not bad, f"missing '*For:' line under the title: {bad}"


def test_contributor_pages_are_not_in_the_user_site() -> None:
    assert not (DOCS / "testing.md").exists() and not (DOCS / "releasing.md").exists()
    assert (ROOT / "CONTRIBUTING.md").is_file()
