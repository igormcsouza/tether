"""`tether run --worktree` docs: a guide page, linked in the nav, that covers the whole flow."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_guide_page_covers_the_flow() -> None:
    page = (ROOT / "docs" / "guides" / "own-branch.md").read_text()
    for needle in ("--worktree", "--worktree-from", "--setup", "tether/", "git worktree remove"):
        assert needle in page, needle
    assert "status" in page and "branch" in page and "commit" in page


def test_guide_is_in_the_nav() -> None:
    assert "guides/own-branch.md" in (ROOT / "mkdocs.yml").read_text()


def test_release_notes_and_agent_interface_mention_it() -> None:
    notes = (ROOT / "docs" / "release-notes.md").read_text().split("## v", 1)[0]
    assert "--worktree" in notes
    assert "worktree" in (ROOT / "docs" / "reference" / "agent-interface.md").read_text()
