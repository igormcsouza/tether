"""#135 docs: the release notes say empty replies are retried and stop the session."""

from __future__ import annotations

from pathlib import Path


def test_release_notes_mention_empty_replies() -> None:
    notes = Path(__file__).resolve().parents[1] / "docs" / "release-notes.md"
    unreleased = notes.read_text().split("## v", 1)[0]
    assert "#135" in unreleased and "empty" in unreleased
