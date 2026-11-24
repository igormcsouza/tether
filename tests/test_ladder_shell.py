"""bench/ladder/shell.py: the opt-in shell kind (terminal work), its tiers and its graders."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

LADDER = Path(__file__).resolve().parent.parent / "bench" / "ladder"


@pytest.fixture
def V(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    monkeypatch.syspath_prepend(str(LADDER))
    for name in ("tasks", "general", "shell", "refs", "base", "validate"):
        sys.modules.pop(name, None)
    return importlib.import_module("validate")  # validate.T is the tasks module


def test_shell_is_opt_in_with_six_rising_tiers(V) -> None:
    T = V.T
    assert T.SHELL_KINDS == ("shell",)
    assert not set(T.SHELL_KINDS) & set(T.GENERAL_KINDS) and "shell" not in T.KINDS
    tasks = T.by_kind("shell")
    assert sorted(t.tier for t in tasks) == [1, 2, 3, 4, 5, 6]
    assert {t.id for t in tasks} == {f"shell-{n}" for n in range(1, 7)}
    for t in tasks:
        assert t.checks or t.ws_checks, t.id


@pytest.mark.parametrize("n", range(1, 7))
def test_untouched_workspace_fails_and_reference_passes(V, n: int) -> None:
    t = V.T.TASKS[f"shell-{n}"]
    start, detail = V.T.grade(t, V.materialize(t))
    assert start < 0.99, (t.id, detail)
    score, detail = V.T.grade(t, V.materialize(t, t.ref))
    assert score >= 0.99, (t.id, detail)


def test_a_partial_rename_scores_between_zero_and_one(V) -> None:
    t = V.T.TASKS["shell-2"]
    ws = V.materialize(t, {"photos/IMG_0001.JPG": None, "photos/img_0001.jpg": "sunrise\n"})
    score, detail = V.T.grade(t, ws)
    assert 0 < score < 1, detail
