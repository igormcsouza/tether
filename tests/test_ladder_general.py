"""bench/ladder/general.py: the non-coding kinds (content, qa, critique, extract), their graders."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

LADDER = Path(__file__).resolve().parent.parent / "bench" / "ladder"
NEW_KINDS = ("content", "qa", "critique", "extract")


@pytest.fixture
def T(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    monkeypatch.syspath_prepend(str(LADDER))
    for name in ("tasks", "general", "refs"):
        sys.modules.pop(name, None)
    return importlib.import_module("tasks")


def _grade(T, task_id: str, text: str | None, tmp_path: Path) -> tuple[float, str]:  # type: ignore[no-untyped-def]
    task = T.TASKS[task_id]
    tmp_path.mkdir(parents=True, exist_ok=True)
    for path, body in T.workspace(task).items():
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text(body)
    if text is not None:
        (tmp_path / task.deliverable).write_text(text)
    return T.grade(task, tmp_path)


def test_every_new_kind_has_rising_tiers_with_a_file_deliverable(T) -> None:
    assert set(T.GENERAL_KINDS) == set(NEW_KINDS)
    for kind in NEW_KINDS:
        tiers = sorted(t.tier for t in T.by_kind(kind))
        assert tiers == list(range(1, len(tiers) + 1)) and 3 <= len(tiers) <= 6, kind
        for t in T.by_kind(kind):
            assert t.deliverable and t.deliverable in t.goal, t.id


def test_non_coding_tasks_do_not_carry_the_shop_project(T) -> None:
    ws = T.workspace(T.TASKS["qa-1"])
    assert not any(p.startswith("shop/") for p in ws), "a document question needs no code base"
    assert any(p.startswith("shop/") for p in T.workspace(T.TASKS["write-1"]))


@pytest.mark.parametrize("kind", NEW_KINDS)
def test_reference_passes_and_missing_or_empty_scores_zero(T, kind: str, tmp_path: Path) -> None:
    from refs import REFS

    for t in T.by_kind(kind):
        d = tmp_path / t.id
        assert _grade(T, t.id, None, d / "none")[0] == 0.0
        assert _grade(T, t.id, "", d / "empty")[0] == 0.0
        score, detail = _grade(T, t.id, REFS[t.id], d / "ref")
        assert score >= 0.99, (t.id, detail)


def test_content_checks_length_banned_words_and_invented_numbers(T, tmp_path: Path) -> None:
    from refs import REFS

    ref = REFS["content-2"]
    padded = ref + " More words." * 80
    score, detail = _grade(T, "content-2", padded, tmp_path / "a")
    assert score < 1 and "words" in detail
    score, detail = _grade(T, "content-1", REFS["content-1"] + " Revolutionary.", tmp_path / "b")
    assert score < 1 and "banned" in detail
    invented = ref + " Sales grew 340% last year."
    score, detail = _grade(T, "content-2", invented, tmp_path / "c")
    assert score < 1 and "invented numbers" in detail


def test_qa_wants_not_in_the_document_and_rejects_a_guess(T, tmp_path: Path) -> None:
    from refs import REFS

    task = T.TASKS["qa-2"]
    assert "not in the document" in task.goal.lower() or "not in the documents" in task.goal.lower()
    guess = REFS["qa-2"].replace("Q4: Not in the document.", "Q4: Yes, free parking is available.")
    assert guess != REFS["qa-2"]
    score, detail = _grade(T, "qa-2", guess, tmp_path)
    assert score < 1 and "Q4" in detail


def test_qa_answers_are_split_by_number(T) -> None:
    import general

    got = general.answers("Q1: twelve\n**Q2.** the\nsecond line\n3) three\n")
    assert got == {1: "twelve", 2: "the\nsecond line", 3: "three"}


def test_qa_hedge_listing_both_prices_fails(T, tmp_path: Path) -> None:
    from refs import REFS

    hedged = REFS["qa-3"].replace("Q1: €25", "Q1: €20 or €25")
    assert hedged != REFS["qa-3"]
    assert _grade(T, "qa-3", hedged, tmp_path)[0] < 1


def test_critique_recall_and_false_alarms_like_review(T, tmp_path: Path) -> None:
    from refs import REFS

    t = T.TASKS["critique-3"]
    first = REFS["critique-3"].splitlines()[0]
    one, _ = _grade(T, "critique-3", first + "\n", tmp_path / "a")
    assert 0 < one < T.pass_threshold(t)
    alarm = REFS["critique-3"] + "- The 14-day free trial is too short and a risk.\n"
    score, detail = _grade(T, "critique-3", alarm, tmp_path / "b")
    assert score < 1 and "false alarm" in detail
    extra = REFS["critique-1"] + "".join(f"- Sound extra point {i}: no quotes.\n" for i in range(6))
    assert _grade(T, "critique-1", extra, tmp_path / "c")[0] == 1.0, "more sound points are fine"


def test_extract_needs_valid_json_with_the_right_values(T, tmp_path: Path) -> None:
    from refs import REFS

    score, detail = _grade(T, "extract-1", "not json", tmp_path / "a")
    assert score == 0 and "JSON" in detail
    fenced = "```json\n" + REFS["extract-1"] + "\n```"
    assert _grade(T, "extract-1", fenced, tmp_path / "b")[0] == 1.0
    wrong = json.loads(REFS["extract-1"])
    wrong["meeting_date"] = "14 March 2026"
    score, detail = _grade(T, "extract-1", json.dumps(wrong), tmp_path / "c")
    assert score < 1 and "meeting_date" in detail


def test_run_skips_tiers_a_kind_does_not_have(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.syspath_prepend(str(LADDER))
    spec = importlib.util.spec_from_file_location("ladder_run_g", LADDER / "run.py")
    assert spec and spec.loader
    lad = importlib.util.module_from_spec(spec)
    sys.modules["ladder_run_g"] = lad
    spec.loader.exec_module(lad)
    seen: list = []

    def fake(model, task, attempt, ctx, out, tether_bin, wall, can_think=True, harness="tether",
             provider="ollama", prev=None):  # fmt: skip
        seen.append(task.id)
        return {"model": model, "task": task.id, "kind": task.kind, "tier": task.tier,
                "attempt": attempt, "think": False, "score": 1.0, "pass": True,
                "run_status": "ok", "wall_s": 1, "detail": "", "harness": harness}  # fmt: skip

    monkeypatch.setattr(lad, "run_attempt", fake)
    monkeypatch.setattr(lad, "capabilities", lambda m: [])
    monkeypatch.setattr(
        sys, "argv",
        ["run.py", "--out", str(tmp_path), "--models", "haiku", "--provider", "p",
         "--kinds", "extract", "--single"],
    )  # fmt: skip
    lad.main()
    assert seen == [t.id for t in sorted(lad.T.by_kind("extract"), key=lambda t: t.tier)]
