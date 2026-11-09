"""Coverage for Harness merging SandboxPolicy.verify_commands into its own gate list."""

from pathlib import Path

from tether.harness import Harness
from tether.sandbox import SandboxPolicy


def test_sandbox_verify_commands_append_when_not_already_present(tmp_path: Path) -> None:
    policy = SandboxPolicy(verify_commands=["pytest -q", "ruff check ."])
    h = Harness(sandbox=policy, db_path=tmp_path / "t.db", verify="ruff check .")
    assert h._verify_commands == ["ruff check .", "pytest -q"]
    assert h.sandbox.verify_commands == ["ruff check .", "pytest -q"]


def test_sandbox_verify_commands_used_when_no_verify_given(tmp_path: Path) -> None:
    policy = SandboxPolicy(verify_commands=["pytest -q"])
    h = Harness(sandbox=policy, db_path=tmp_path / "t.db")
    assert h._verify_commands == ["pytest -q"]
    assert h.sandbox.verify_commands == ["pytest -q"]


def test_load_allow_file_missing_is_empty(tmp_path: Path) -> None:
    from tether.sandbox import load_allow_file

    assert load_allow_file(tmp_path) == ()


def test_allow_file_merged_by_harness(tmp_path: Path) -> None:
    (tmp_path / ".tether").mkdir()
    (tmp_path / ".tether" / "allow.json").write_text('{"allow": ["git push"]}')
    policy = SandboxPolicy(workspace_root=tmp_path, allow_outside=("gh",))
    h = Harness(sandbox=policy, db_path=tmp_path / "t.db")
    assert h.sandbox.allow_outside == ("git push", "gh")
    assert policy.allow_outside == ("gh",)


def test_allow_file_write_refused_and_unchanged(tmp_path: Path) -> None:
    import pytest

    from tether.sandbox import SandboxViolationError

    (tmp_path / ".tether").mkdir()
    path = tmp_path / ".tether" / "allow.json"
    path.write_text('{"allow": ["git push"]}')
    policy = SandboxPolicy(workspace_root=tmp_path)
    with pytest.raises(SandboxViolationError):
        policy.resolve_safe_path(".tether/allow.json", write=True)
    assert path.read_text() == '{"allow": ["git push"]}'


def test_children_keep_allow_list(tmp_path: Path) -> None:
    parent = SandboxPolicy(workspace_root=tmp_path, allow_outside=("git push", "gh"))
    assert parent.attenuate().allow_outside == ("git push", "gh")
    assert parent.attenuate(child_allow_outside=None).allow_outside == ("git push", "gh")


def test_mcp_allow_reaches_policy(tmp_path: Path, monkeypatch) -> None:
    import asyncio

    import pytest

    pytest.importorskip("mcp")
    from tests.conftest import FakeScriptedProvider
    from tether.mcp import TetherMCP, ToolError
    from tether.providers.base import ActionCall, ModelResponse

    done = ModelResponse(content="", action=ActionCall(cmd="done", stdin="ok"))
    monkeypatch.setattr(
        "tether.harness.resolve_provider", lambda *a, **k: FakeScriptedProvider([done])
    )
    ws = tmp_path / "root"
    ws.mkdir()
    impl = TetherMCP(db_path=tmp_path / "t.db", workspace=ws)
    out = asyncio.run(impl.call("tether_run", {"goal": "g", "wait": False, "allow": ["gh"]}))
    rec = impl.store.get_session(out["id"])
    assert rec is not None
    assert rec.sandbox_config["allow_outside"] == ["gh"]
    with pytest.raises(ToolError):
        asyncio.run(impl.call("tether_run", {"goal": "g", "wait": False, "allow": [""]}))


def test_non_git_command_is_not_git_unsafe() -> None:
    from tether.sandbox import _git_unsafe_option

    assert _git_unsafe_option("gh pr create --draft") is False
