"""Resume a failed or waiting pipeline from its first unfinished stage (issue #35)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from tests.conftest import FakeScriptedProvider
from tether import ActionCall, Harness, ModelResponse, api, register_provider
from tether.cli import _async_main
from tether.harness import PipelineResumeError

MANIFEST = """name: resume-pipe
stages:
  - id: s1
    model: resume-x/m
    goal: one
  - id: s2
    model: resume-x/m
    goal: two {{goal}}
    max_steps: 1
  - id: s3
    model: resume-x/m
    goal: three {{s2.session_id}}
"""


def _respond(cmd: str, stdin: str) -> ModelResponse:
    return ModelResponse(content="", action=ActionCall(cmd=cmd, stdin=stdin))


@pytest.fixture
def scripted() -> dict[str, Any]:
    slot: dict[str, Any] = {}
    register_provider("resume-x", lambda name: slot["p"])
    return slot


def _harness(tmp_path: Path) -> Harness:
    return Harness(db_path=tmp_path / "tether.db", tools=["mem"])


async def _fail_first_run(tmp_path: Path, scripted: dict[str, Any]) -> tuple[Harness, Path, str]:
    manifest = tmp_path / "pipe.yaml"
    manifest.write_text(MANIFEST, encoding="utf-8")
    scripted["p"] = FakeScriptedProvider([_respond("done", "first"), _respond("bash", "echo hi")])
    harness = _harness(tmp_path)
    failed = await harness.run_pipeline(manifest, "Root goal")
    assert failed.status == "WAITING_INPUT"
    return harness, manifest, failed.id


async def test_resume_reruns_only_failed_stage_and_reuses_completed(
    tmp_path: Path, scripted: dict[str, Any]
) -> None:
    harness, _, pid = await _fail_first_run(tmp_path, scripted)
    provider = FakeScriptedProvider([_respond("done", "second"), _respond("done", "third")])
    scripted["p"] = provider
    resumed = await harness.resume_pipeline(pid)
    assert resumed.status == "COMPLETED"
    assert len(provider.recorded_calls) == 2


async def test_resume_does_not_rerun_completed_stage(
    tmp_path: Path, scripted: dict[str, Any]
) -> None:
    harness, _, pid = await _fail_first_run(tmp_path, scripted)
    scripted["p"] = FakeScriptedProvider([_respond("done", "second"), _respond("done", "third")])
    await harness.resume_pipeline(pid)
    children = harness.store.list_sessions(parent_id=pid)
    assert len([c for c in children if c.goal.startswith("one")]) == 1


async def test_resume_stage_three_digest_includes_reused_stage_one(
    tmp_path: Path, scripted: dict[str, Any]
) -> None:
    harness, _, pid = await _fail_first_run(tmp_path, scripted)
    scripted["p"] = FakeScriptedProvider([_respond("done", "second"), _respond("done", "third")])
    await harness.resume_pipeline(pid)
    children = harness.store.list_sessions(parent_id=pid)
    stage_one = next(c for c in children if c.goal.startswith("one"))
    stage_three = next(c for c in children if c.goal.startswith("three"))
    assert stage_one.id in stage_three.goal
    assert "[Upstream Pipeline Stages]" in stage_three.goal


async def test_resume_completed_pipeline_is_noop(
    tmp_path: Path, scripted: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    manifest = tmp_path / "pipe.yaml"
    manifest.write_text(MANIFEST, encoding="utf-8")
    scripted["p"] = FakeScriptedProvider([_respond("done", "a")] * 3)
    harness = _harness(tmp_path)
    done_rec = await harness.run_pipeline(manifest, "Root goal")
    assert done_rec.status == "COMPLETED"
    before = len(harness.store.list_sessions(parent_id=done_rec.id))
    again = await harness.resume_pipeline(done_rec.id)
    assert again.status == "COMPLETED"
    assert len(harness.store.list_sessions(parent_id=done_rec.id)) == before
    capsys.readouterr()
    code = await _async_main(
        ["pipeline", "--resume", done_rec.id, "--db", str(tmp_path / "tether.db")]
    )
    assert code == 0
    assert (
        capsys.readouterr().out
        == f"Pipeline `{done_rec.id}` is already COMPLETED; nothing to resume.\n"
    )


async def test_resume_unknown_id_and_plain_session_exit_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db = str(tmp_path / "tether.db")
    assert await _async_main(["pipeline", "--resume", "nope", "--db", db]) == api.EXIT_USAGE
    assert "not found" in capsys.readouterr().err
    plain = _harness(tmp_path).store.create_session(goal="plain")
    assert await _async_main(["pipeline", "--resume", plain.id, "--db", db]) == api.EXIT_USAGE
    assert "is not a pipeline" in capsys.readouterr().err


async def test_resume_running_pipeline_exit_1(tmp_path: Path, scripted: dict[str, Any]) -> None:
    harness, _, pid = await _fail_first_run(tmp_path, scripted)
    harness.store.update_session(pid, status="RUNNING", pid=os.getpid())
    with pytest.raises(PipelineResumeError) as exc:
        await harness.resume_pipeline(pid)
    assert "RUNNING" in str(exc.value)


async def test_resume_missing_manifest_exit_1(
    tmp_path: Path, scripted: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    _, manifest, pid = await _fail_first_run(tmp_path, scripted)
    manifest.unlink()
    capsys.readouterr()
    code = await _async_main(["pipeline", "--resume", pid, "--db", str(tmp_path / "tether.db")])
    assert code == api.EXIT_USAGE
    err = capsys.readouterr().err
    assert "cannot resume pipeline" in err
    assert str(manifest.resolve()) in err


async def test_resume_flag_conflicts_and_stored_source(
    tmp_path: Path, scripted: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    harness, manifest, pid = await _fail_first_run(tmp_path, scripted)
    db = str(tmp_path / "tether.db")
    assert (
        await _async_main(["pipeline", "--resume", pid, str(manifest), "--db", db])
        == api.EXIT_USAGE
    )
    assert (
        await _async_main(["pipeline", "--resume", pid, "--headless", "--db", db]) == api.EXIT_USAGE
    )
    assert await _async_main(["pipeline", str(manifest), "--db", db]) == api.EXIT_USAGE
    assert await _async_main(["pipeline", "--db", db]) == api.EXIT_USAGE
    capsys.readouterr()
    stored = harness.store.get_session(pid)
    assert stored is not None
    assert stored.sandbox_config["pipeline_source"] == str(manifest.resolve())


async def test_resume_without_stored_source_or_invalid_manifest_exit_1(
    tmp_path: Path, scripted: dict[str, Any]
) -> None:
    harness = _harness(tmp_path)
    inline = harness.create_pipeline_session(
        {"name": "inline", "stages": [{"id": "s1", "model": "resume-x/m", "goal": "one"}]},
        "Root goal",
    )
    with pytest.raises(PipelineResumeError, match="cannot resume pipeline"):
        await harness.resume_pipeline(inline.id)
    _, manifest, pid = await _fail_first_run(tmp_path, scripted)
    manifest.write_text("- just\n- a list\n", encoding="utf-8")
    with pytest.raises(PipelineResumeError, match="cannot resume pipeline"):
        await harness.resume_pipeline(pid)


async def test_resume_corrupt_stored_pipeline_exit_1(
    tmp_path: Path, scripted: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    harness, _, pid = await _fail_first_run(tmp_path, scripted)

    def _broken(data: dict[str, Any]) -> None:
        raise KeyError("stages")

    monkeypatch.setattr("tether.pipeline.Pipeline.from_dict", _broken)
    with pytest.raises(PipelineResumeError, match="cannot resume pipeline") as exc:
        await harness.resume_pipeline(pid)
    assert "stored pipeline is invalid" in str(exc.value)
