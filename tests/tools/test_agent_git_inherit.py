"""agent spawn child config inherits allow_outside only narrowed (S4a)."""

from __future__ import annotations

from pathlib import Path

from tether import SandboxPolicy, SkillLoader, SQLiteStore
from tether.tools.agent import make_agent_tool


async def test_spawn_child_keeps_only_explicit_git_subcommands(tmp_path: Path) -> None:
    store = SQLiteStore(db_path=tmp_path / "tether.db")
    parent = store.create_session("Parent")
    sk_dir = tmp_path / "skills"
    sk_dir.mkdir()
    parent_sb = SandboxPolicy(workspace_root=tmp_path, allow_outside=("git config user.name", "gh"))
    aspec = make_agent_tool(
        store=store,
        parent_session_id=parent.id,
        default_model="ollama/qwen3.5:9b",
        parent_sandbox=parent_sb,
        skill_loader=SkillLoader(search_dirs=[sk_dir]),
        worker_spawner=lambda sid: 123,
        wait_timeout=0.1,
    )
    cid = await aspec.invoke(["spawn", "SubGoal"])
    rec = store.get_session(cid)
    assert rec is not None
    child = SandboxPolicy.from_dict(rec.sandbox_config)
    assert child.allow_outside == ("git config user.name", "gh")


async def test_spawn_child_bare_git_entry_stays_bare(tmp_path: Path) -> None:
    store = SQLiteStore(db_path=tmp_path / "tether.db")
    parent = store.create_session("Parent")
    sk_dir = tmp_path / "skills"
    sk_dir.mkdir()
    parent_sb = SandboxPolicy(workspace_root=tmp_path, allow_outside=("git",))
    aspec = make_agent_tool(
        store=store,
        parent_session_id=parent.id,
        default_model="ollama/qwen3.5:9b",
        parent_sandbox=parent_sb,
        skill_loader=SkillLoader(search_dirs=[sk_dir]),
        worker_spawner=lambda sid: 123,
        wait_timeout=0.1,
    )
    cid = await aspec.invoke(["spawn", "SubGoal"])
    rec = store.get_session(cid)
    assert rec is not None
    child = SandboxPolicy.from_dict(rec.sandbox_config)
    assert child.allow_outside == ("git",)
