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


def test_shell_is_opt_in_with_nine_rising_tiers(V) -> None:
    T = V.T
    assert T.SHELL_KINDS == ("shell",)
    assert not set(T.SHELL_KINDS) & set(T.GENERAL_KINDS) and "shell" not in T.KINDS
    tasks = T.by_kind("shell")
    assert sorted(t.tier for t in tasks) == list(range(1, 10))
    assert {t.id for t in tasks} == {f"shell-{n}" for n in range(1, 10)}
    for t in tasks:
        assert t.checks or t.ws_checks, t.id


@pytest.mark.parametrize("n", range(1, 10))
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


def test_one_duplicate_left_behind_scores_between_zero_and_one(V) -> None:
    t = V.T.TASKS["shell-8"]
    left = "downloads/b/config.ini"  # the tie that should have gone: the rest is done right
    removed = sorted(p for p in t.ref if p != "dupes.txt" and t.ref[p] is None and p != left)
    dupes = "".join(f"{p}\n" for p in removed)
    ws = V.materialize(t, {**t.ref, left: t.files[left], "dupes.txt": dupes})
    score, detail = V.T.grade(t, ws)
    assert 0 < score < 1, detail


def test_report_hard_coded_for_logs_fails_on_an_unseen_log_folder(V) -> None:
    t = V.T.TASKS["shell-9"]
    # right for logs/, ignores its argument
    hard_coded = "#!/bin/bash\ncat <<'EOF'\n" + t.ref["report.csv"] + "EOF\n"
    ws = V.materialize(t, {**t.ref, "report.sh": hard_coded})
    score, detail = V.T.grade(t, ws)
    assert 0 < score < 1, detail
    assert "not seen" in detail, detail
