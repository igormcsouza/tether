"""The benchmarks page reports the current score and how to reproduce it (#154)."""

from __future__ import annotations

from pathlib import Path

PAGE = (Path(__file__).resolve().parents[1] / "docs" / "benchmarks.md").read_text()


def test_reports_the_polyglot_score_and_the_method() -> None:
    assert "Polyglot-Python" in PAGE and "polyglot-fast" in PAGE
    assert "v0.2.8" in PAGE and "restored before grading" in PAGE


def test_shows_how_to_reproduce() -> None:
    assert "bench/run.py" in PAGE and "bench/report.py" in PAGE and "--trials 2" in PAGE


def test_old_video_benchmark_is_gone() -> None:
    for stale in ("Manim", "claude-sonnet-4-6", "gemma4:e4b"):
        assert stale not in PAGE
