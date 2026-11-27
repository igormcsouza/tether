"""AD-57: a sub-agent gets its parent's tools and never one the parent lacks."""

from __future__ import annotations

from pathlib import Path

from tether.sandbox import SandboxPolicy
from tether.skills import SkillLoader
from tether.store import SQLiteStore
from tether.tools.agent import make_agent_tool


def _spawn_tool(tmp_path: Path, parent_tools: list[str] | None, skills: Path | None = None):  # type: ignore[no-untyped-def]
    store = SQLiteStore(db_path=tmp_path / "t.db")
    parent = store.create_session(goal="parent", model="m", tools=parent_tools or [])
    spec = make_agent_tool(
        store=store,
        parent_session_id=parent.id,
        default_model="m",
        parent_sandbox=SandboxPolicy(workspace_root=tmp_path),
        skill_loader=SkillLoader(search_dirs=[skills] if skills else []),
        worker_spawner=lambda sid: None,
        parent_tools=parent_tools,
    )
    return store, spec


def _child_tools(store: SQLiteStore, out: str) -> list[str]:
    rec = store.get_session(out.split()[0])
    assert rec is not None
    return rec.tools


async def test_child_without_tools_gets_the_parents(tmp_path: Path) -> None:
    store, spec = _spawn_tool(tmp_path, ["bash", "edit", "agent"])
    out = await spec.invoke(["spawn", "count the words in a.txt"])
    assert _child_tools(store, out) == ["bash", "edit", "agent"] and "[note]" not in out


async def test_a_tool_the_parent_lacks_is_dropped_and_named(tmp_path: Path) -> None:
    store, spec = _spawn_tool(tmp_path, ["web", "agent"])
    out = await spec.invoke(["spawn", "--tools", "bash,web", "goal"])
    assert _child_tools(store, out) == ["web"]
    assert "[note] started with web, not bash: a child gets only tools this session has" in out


async def test_all_means_the_parents_tools(tmp_path: Path) -> None:
    store, spec = _spawn_tool(tmp_path, ["edit", "agent"])
    out = await spec.invoke(["spawn", "--tools", "all,edit", "goal"])
    assert _child_tools(store, out) == ["edit", "agent"] and "[note]" not in out


async def test_skill_tools_are_narrowed_too(tmp_path: Path) -> None:
    sk = tmp_path / "skills"
    sk.mkdir()
    (sk / "net.md").write_text("---\nname: net\ntools: [web, bash, lookup]\n---\nBody")
    store, spec = _spawn_tool(tmp_path, ["bash", "agent"], skills=sk)
    out = await spec.invoke(["spawn", "--skill", "net", "goal"])
    assert _child_tools(store, out) == ["bash", "lookup"]  # the skill's own tool is its own
    assert "not web:" in out


async def test_nothing_left_falls_back_to_the_parents_tools(tmp_path: Path) -> None:
    """`--tools t` copied from the usage line: the child still gets the parent's tools."""
    store, spec = _spawn_tool(tmp_path, ["bash", "agent"])
    out = await spec.invoke(["spawn", "--tools", "t,web", "goal"])
    assert _child_tools(store, out) == ["bash", "agent"]
    assert "started with bash, agent, not t, web" in out


async def test_a_parent_with_no_tools_says_so(tmp_path: Path) -> None:
    store, spec = _spawn_tool(tmp_path, [])
    out = await spec.invoke(["spawn", "--tools", "bash", "goal"])
    assert _child_tools(store, out) == [] and "started with no tools, not bash" in out


async def test_direct_sdk_use_leaves_tools_as_asked(tmp_path: Path) -> None:
    store, spec = _spawn_tool(tmp_path, None)
    out = await spec.invoke(["spawn", "--tools", "bash", "goal"])
    assert _child_tools(store, out) == ["bash"]
