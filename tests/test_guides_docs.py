"""Story guides show a real command and say what to do when it goes wrong (#152)."""

from __future__ import annotations

from pathlib import Path

GUIDES = sorted((Path(__file__).resolve().parents[1] / "docs" / "guides").glob("*.md"))


def test_there_are_four_story_guides() -> None:
    assert len(GUIDES) >= 4


def test_each_guide_has_a_command_an_output_and_a_failure_section() -> None:
    for g in GUIDES:
        text = g.read_text()
        assert "```bash" in text or "```python" in text, g.name
        assert "```text" in text or "```json" in text, f"{g.name}: no real output shown"
        assert "## When it goes wrong" in text, g.name
        assert text.splitlines()[2].startswith("*For:"), g.name
