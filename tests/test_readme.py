"""The README is the project pitch: short, current and pointing at the docs (#63)."""

from __future__ import annotations

from pathlib import Path

README = (Path(__file__).resolve().parents[1] / "README.md").read_text()


def test_readme_is_short_and_has_the_pitch_sections() -> None:
    assert len(README.splitlines()) <= 170
    for heading in (
        "## Why Tether",
        "## How well does it work",
        "## Why this and not that",
        "## Install and first run",
        "## Contributing",
    ):
        assert heading in README, heading


def test_readme_points_to_docs_and_contributing_and_not_to_old_benchmarks() -> None:
    assert "igormcsouza.github.io/tether" in README and "CONTRIBUTING.md" in README
    for stale in ("YouTube Short", "Manim", "claude-sonnet-4-6", "providers.yaml\n```"):
        assert stale not in README
    assert "Polyglot-Python" in README
