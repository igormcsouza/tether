"""Unit and integration tests for deterministic multi-stage pipelines (tether/pipeline.py)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.conftest import FakeScriptedProvider
from tether import (
    ActionCall,
    Harness,
    ModelResponse,
    Pipeline,
    PipelineSpec,
    PipelineStage,
    SandboxPolicy,
    load_pipeline,
    parse_pipeline_yaml,
    register_provider,
)
from tether.context import estimate_tokens
from tether.pipeline import _normalize_str_list


def test_pipeline_manifest_parsing_and_validation(tmp_path: Path) -> None:
    """Verify YAML/dict parsing, stage normalization, and validation errors."""
    assert PipelineSpec is Pipeline
    assert _normalize_str_list(None) == []
    assert _normalize_str_list(["bash", " edit "]) == ["bash", "edit"]
    assert _normalize_str_list("bash, edit") == ["bash", "edit"]

    yaml_text = """
name: secure-feature-pipeline
description: Spec -> Implement -> Security Audit
sandbox: workspace-write
max_steps: 10
stages:
  - id: spec
    skill: architect
    model: anthropic/claude-3-7-sonnet-latest
    tools: [edit, mem]
    goal: "Write a concise technical spec for: {{goal}}"

  - id: implement
    skill: coder
    model: ollama/qwen3.5:9b
    tools: "bash,edit"
    verify: "pytest -q"
    max_steps: 12
    goal: "Implement the feature according to the spec from stage `spec` ({{spec.id}})."

  - id: security_audit
    model: openai/gpt-4o-mini
    sandbox: read-only
    verify: ["ruff check ."]
    goal: "Audit workspace changes against {{spec.session_id}}."
"""
    manifest_file = tmp_path / "workflow.yaml"
    manifest_file.write_text(yaml_text, encoding="utf-8")

    loaded = load_pipeline(manifest_file)
    assert loaded.name == "secure-feature-pipeline"
    assert loaded.description == "Spec -> Implement -> Security Audit"
    assert loaded.sandbox == "workspace-write"
    assert loaded.max_steps == 10
    assert len(loaded.stages) == 3
    assert loaded.stages[0].tools == ["edit", "mem"]
    assert loaded.stages[1].tools == ["bash", "edit"]
    assert loaded.stages[1].verify == ["pytest -q"]
    assert loaded.stages[1].max_steps == 12
    assert loaded.stages[2].sandbox == "read-only"
    assert loaded.stages[2].verify == ["ruff check ."]

    roundtrip = Pipeline.from_dict(loaded.to_dict())
    assert roundtrip.to_dict() == loaded.to_dict()

    with pytest.raises(ValueError, match="cannot be empty"):
        PipelineStage(id="   ", goal="valid")
    with pytest.raises(ValueError, match="goal cannot be empty"):
        PipelineStage(id="s1", goal="   ")
    with pytest.raises(ValueError, match="Unsupported stage sandbox"):
        PipelineStage(id="s1", goal="valid", sandbox="privileged")
    with pytest.raises(ValueError, match="at least one stage"):
        Pipeline(name="empty", stages=[])
    with pytest.raises(ValueError, match="Duplicate stage id"):
        Pipeline(
            name="dup",
            stages=[PipelineStage(id="s1", goal="g1"), PipelineStage(id="s1", goal="g2")],
        )
    with pytest.raises(ValueError, match="Unsupported pipeline sandbox"):
        Pipeline(
            name="bad_sb",
            stages=[PipelineStage(id="s1", goal="g1")],
            sandbox="root",
        )
    with pytest.raises(ValueError, match="top-level mapping"):
        parse_pipeline_yaml("- just a list")
    with pytest.raises(ValueError, match="non-empty `stages` list"):
        Pipeline.from_dict({"name": "no_stages", "stages": []})
    with pytest.raises(ValueError, match="must be a mapping"):
        Pipeline.from_dict({"name": "bad_stage", "stages": ["not-a-dict"]})


async def test_multi_model_routing_fts5_handoff_and_sandbox_monotonicity(
    tmp_path: Path,
) -> None:
    """Verify multi-model routing, bounded FTS5 RAG handoffs, and sandbox attenuation."""
    ws = tmp_path / "ws"
    ws.mkdir()
    sk_dir = tmp_path / "skills"
    sk_dir.mkdir()
    (sk_dir / "architect.md").write_text(
        "---\nname: architect\ndescription: Spec writer\ntools: [mem]\n---\nWrite clear specs.",
        encoding="utf-8",
    )
    custom_sk = sk_dir / "coder"
    custom_sk.mkdir()
    (custom_sk / "SKILL.md").write_text(
        "---\n"
        "name: coder\n"
        "description: Tactical coder\n"
        "model: pipe-slm/qwen3.5:9b\n"
        "tools: [edit, stamp]\n"
        "verify:\n"
        '  - python3 -c "import pathlib, sys; '
        "sys.exit(0 if pathlib.Path('auth.py').exists() else 1)\"\n"
        "---\n"
        "Implement code cleanly.",
        encoding="utf-8",
    )
    (custom_sk / "tools.py").write_text(
        "from tether import tool\n"
        "@tool(name='stamp', description='Stamp build metadata')\n"
        "def stamp() -> str:\n"
        "    return 'stamped-v1'\n",
        encoding="utf-8",
    )

    spec_provider = FakeScriptedProvider(
        [
            ModelResponse(
                content="",
                action=ActionCall(
                    cmd="done",
                    stdin=(
                        "# Technical Specification: HMAC Token Validator\n"
                        "The module `auth.py` must define `ALGORITHM = 'HMAC-SHA256'` "
                        "and enforce constant-time signature comparison.\n\n"
                        "# Security Invariants\n"
                        "Reject empty keys and expired timestamps deterministically."
                    ),
                ),
                prompt_tokens=120,
                completion_tokens=45,
            )
        ]
    )
    impl_provider = FakeScriptedProvider(
        [
            # Stage 2 queries Stage 1's FTS5 chunks via `agent query --all`
            ModelResponse(
                content="",
                action=ActionCall(cmd='agent query --all "ALGORITHM HMAC" --top 1'),
                prompt_tokens=140,
                completion_tokens=20,
            ),
            ModelResponse(
                content="",
                action=ActionCall(cmd="stamp"),
                prompt_tokens=160,
                completion_tokens=15,
            ),
            ModelResponse(
                content="",
                action=ActionCall(
                    cmd="edit write auth.py",
                    stdin="ALGORITHM = 'HMAC-SHA256'\n",
                ),
                prompt_tokens=175,
                completion_tokens=25,
            ),
            ModelResponse(
                content="",
                action=ActionCall(
                    cmd="done",
                    stdin="Implemented `auth.py` with `ALGORITHM = 'HMAC-SHA256'`.",
                ),
                prompt_tokens=190,
                completion_tokens=25,
            ),
        ]
    )
    audit_provider = FakeScriptedProvider(
        [
            # Stage 3 runs in read-only sandbox: attempting `edit write` is blocked
            ModelResponse(
                content="",
                action=ActionCall(cmd="edit write pwned.txt", stdin="should fail"),
                prompt_tokens=130,
                completion_tokens=20,
            ),
            ModelResponse(
                content="",
                action=ActionCall(
                    cmd="done",
                    stdin="Audit passed: `auth.py` matches spec and read-only jail held.",
                ),
                prompt_tokens=155,
                completion_tokens=30,
            ),
        ]
    )

    register_provider("pipe-frontier", lambda name: spec_provider)
    register_provider("pipe-slm", lambda name: impl_provider)
    register_provider("pipe-audit", lambda name: audit_provider)

    pipeline_yaml = """
name: secure-feature-pipeline
stages:
  - id: spec
    skill: architect
    model: pipe-frontier/claude-3-7-sonnet
    goal: "Write a concise technical spec for: {{goal}}"

  - id: implement
    skill: coder
    goal: "Implement the feature according to the spec from stage `spec` ({{spec.session_id}})."

  - id: security_audit
    model: pipe-audit/gpt-4o-mini
    sandbox: read-only
    tools: [edit]
    goal: "Audit workspace changes against stage `spec` ({{spec.id}})."
"""

    sandbox = SandboxPolicy(profile="workspace-write", workspace_root=ws, use_kernel_sandbox=False)
    harness = Harness(
        db_path=tmp_path / "tether.db",
        sandbox=sandbox,
        skill_search_dirs=[sk_dir],
    )

    root_rec = await harness.run_pipeline(pipeline_yaml, "Build HMAC token validator")
    assert root_rec.status == "COMPLETED"
    assert "Audit passed" in (root_rec.result or "")
    assert root_rec.step_count == 3
    assert (ws / "auth.py").read_text(encoding="utf-8") == "ALGORITHM = 'HMAC-SHA256'\n"
    assert not (ws / "pwned.txt").exists()

    # Verify each stage ran in its own isolated child SessionRecord linked via parent_id
    stage_records = harness.store.list_sessions(parent_id=root_rec.id)
    assert len(stage_records) == 3
    assert [s.model for s in stage_records] == [
        "pipe-frontier/claude-3-7-sonnet",
        "pipe-slm/qwen3.5:9b",
        "pipe-audit/gpt-4o-mini",
    ]
    assert [s.status for s in stage_records] == ["COMPLETED", "COMPLETED", "COMPLETED"]
    assert stage_records[0].sandbox_config["profile"] == "workspace-write"
    assert stage_records[1].sandbox_config["profile"] == "workspace-write"
    assert stage_records[2].sandbox_config["profile"] == "read-only"

    # Verify KV-cache static prefix immutability within multi-step stage 2
    stage2_sys = impl_provider.recorded_calls[0][0]["content"]
    for call_msgs in impl_provider.recorded_calls:
        assert call_msgs[0]["content"] == stage2_sys

    # Verify stage 2 received a compact digest of stage 1 and retrieved the FTS5 chunk
    stage2_initial_user = impl_provider.recorded_calls[0][1]["content"]
    assert "[Upstream Pipeline Stages]:" in stage2_initial_user
    assert stage_records[0].id in stage2_initial_user
    assert estimate_tokens(stage2_initial_user) < 160
    stage2_after_query = "\n".join(m["content"] for m in impl_provider.recorded_calls[1])
    assert "HMAC-SHA256" in stage2_after_query

    # Verify stage 3's write attempt was blocked by its read-only sandbox
    stage3_step2_prompt = "\n".join(m["content"] for m in audit_provider.recorded_calls[1])
    assert "read-only" in stage3_step2_prompt


async def test_pipeline_sandbox_cannot_escalate_root_readonly(tmp_path: Path) -> None:
    """Verify Rule 6: `workspace-write` stage under `read-only` root stays `read-only`."""
    provider = FakeScriptedProvider(
        [ModelResponse(content="", action=ActionCall(cmd="done", stdin="Read-only stage ok"))]
    )
    register_provider("pipe-ro", lambda name: provider)

    pipe_dict = {
        "name": "ro-root-test",
        "stages": [
            {
                "id": "try_escalate",
                "model": "pipe-ro/model",
                "sandbox": "workspace-write",
                "tools": ["edit"],
                "goal": "Try to run with workspace-write",
            }
        ],
    }
    root_sandbox = SandboxPolicy(profile="read-only", workspace_root=tmp_path)
    harness = Harness(db_path=tmp_path / "tether.db", sandbox=root_sandbox)
    root_rec = await harness.run_pipeline(pipe_dict, "Audit only")
    assert root_rec.status == "COMPLETED"
    children = harness.store.list_sessions(parent_id=root_rec.id)
    assert len(children) == 1
    assert children[0].sandbox_config["profile"] == "read-only"


async def test_pipeline_early_abort_on_stage_failure_and_waiting_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify early abort when a stage fails, asks for input, or references a missing skill."""
    monkeypatch.setattr(
        "tether.harness.subprocess.Popen",
        lambda *a, **kw: type("FakePopen", (), {"pid": 5151})(),
    )
    stage2_called = False

    class FailingStage1Provider:
        model_name = "fail-stage"

        async def generate(self, messages: Any, tools: Any) -> ModelResponse:
            raise RuntimeError("stage 1 provider error")

    class NeverReachedStage2Provider:
        model_name = "stage2"

        async def generate(self, messages: Any, tools: Any) -> ModelResponse:
            nonlocal stage2_called
            stage2_called = True
            return ModelResponse(content="", action=ActionCall(cmd="done", stdin="stage 2"))

    register_provider("pipe-fail1", lambda name: FailingStage1Provider())
    register_provider("pipe-never2", lambda name: NeverReachedStage2Provider())

    pipeline = Pipeline(
        name="abort-test",
        stages=[
            PipelineStage(id="s1", model="pipe-fail1/m", goal="Run s1"),
            PipelineStage(id="s2", model="pipe-never2/m", goal="Run s2"),
        ],
    )
    harness = Harness(db_path=tmp_path / "tether.db", tools=["mem"])
    aborted = await harness.run_pipeline(pipeline, "Goal that aborts on stage 1")
    assert aborted.status == "FAILED"
    assert "Stage `s1`" in (aborted.result or "")
    assert not stage2_called
    assert len(harness.store.list_sessions(parent_id=aborted.id)) == 1

    # Missing skill in stage
    bad_skill_pipe = Pipeline(
        name="missing-skill-pipe",
        stages=[PipelineStage(id="s1", skill="nonexistent_skill_xyz", goal="Run")],
    )
    bad_skill_rec = await harness.run_pipeline(bad_skill_pipe, "Goal")
    assert bad_skill_rec.status == "FAILED"
    assert "not found" in (bad_skill_rec.result or "")

    # Stage pausing in WAITING_INPUT via `done --ask`
    ask_provider = FakeScriptedProvider(
        [ModelResponse(content="", action=ActionCall(cmd="done --ask", stdin="Which region?"))]
    )
    register_provider("pipe-ask", lambda name: ask_provider)
    ask_file = tmp_path / "ask_pipe.yaml"
    ask_file.write_text(
        "name: ask-pipe\nstages:\n  - id: clarify\n    model: pipe-ask/m\n    goal: Ask user\n",
        encoding="utf-8",
    )
    waiting_rec = await harness.run_pipeline(str(ask_file), "Deploy cluster")
    assert waiting_rec.status == "WAITING_INPUT"
    assert "Which region?" in (waiting_rec.result or "")

    # Headless spawn_pipeline
    spawned_id = harness.spawn_pipeline(ask_file, "Headless pipeline")
    assert spawned_id.startswith("ses_")
