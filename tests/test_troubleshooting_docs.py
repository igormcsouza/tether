"""Troubleshooting is organised by symptom and carries no issue history (#153)."""

from __future__ import annotations

import re
from pathlib import Path

PAGE = (Path(__file__).resolve().parents[1] / "docs" / "troubleshooting.md").read_text()


def test_no_version_archaeology_or_tracker_copies() -> None:
    assert not re.search(r"[Ff]ixed in v\d", PAGE)
    assert "Known limitations" not in PAGE and "Model notes" not in PAGE
    assert not re.search(r"\(\[?#\d+", PAGE), "issue numbers belong in the tracker, not the page"


def test_known_issues_point_to_the_label() -> None:
    assert "label%3Aknown-issue" in PAGE


def test_every_entry_has_cause_and_fix() -> None:
    entries = re.split(r"^### ", PAGE, flags=re.MULTILINE)[1:]
    assert len(entries) >= 12
    for e in entries:
        assert "**Cause.**" in e and "**Fix.**" in e, e.splitlines()[0]
