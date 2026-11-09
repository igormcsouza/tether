"""The network pattern is documented in the sandbox tutorial and linked from own-branch (#124)."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TUTORIAL = ROOT / "docs" / "tutorial" / "security-and-sandbox.md"
OWN_BRANCH = ROOT / "docs" / "guides" / "own-branch.md"
HEADING = "Install with the network, work without it"
COMMAND = (
    'tether run --worktree --setup "uv sync" --no-network --verify "uv run pytest -q" "<goal>"'
)


def _slug(heading: str) -> str:
    # Same rule the docs use for anchors: lowercase, drop punctuation, spaces to hyphens.
    text = re.sub(r"[^\w\s-]", "", heading.strip().lower())
    return re.sub(r"\s+", "-", text)


def _section(text: str, heading: str) -> str:
    # Body of one '## ' section, up to the next '## ' heading. Whole-file matches would pass
    # vacuously when the flags are mentioned elsewhere on the page.
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if line.strip() == f"## {heading}"), None)
    assert start is not None, f"missing section '## {heading}'"
    body: list[str] = []
    for line in lines[start + 1 :]:
        if line.startswith("## "):
            break
        body.append(line)
    return "\n".join(body)


def test_network_pattern_documented() -> None:
    assert TUTORIAL.is_file(), f"missing {TUTORIAL}"
    section = _section(TUTORIAL.read_text(encoding="utf-8"), HEADING)
    assert section.strip(), "section is empty"
    assert COMMAND in section, "exact command from the card is missing from the section"
    for flag in ("--setup", "--no-network", "--worktree"):
        assert flag in section, f"{flag} not explained in the section"
    for term in ("bwrap", "network"):
        assert term in section, f"{term} not mentioned in the section"


def test_own_branch_links_network_section() -> None:
    assert OWN_BRANCH.is_file(), f"missing {OWN_BRANCH}"
    assert TUTORIAL.is_file(), f"missing {TUTORIAL}"
    # The anchor is derived from the tutorial heading, so a renamed heading breaks this test.
    assert f"## {HEADING}" in TUTORIAL.read_text(encoding="utf-8"), "link target heading missing"
    link = f"](../tutorial/security-and-sandbox.md#{_slug(HEADING)})"
    assert link in OWN_BRANCH.read_text(encoding="utf-8"), f"own-branch.md lacks link {link}"
