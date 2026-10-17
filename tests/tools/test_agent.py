"""Unit tests for tether/tools/agent.py (spawn, status, wait, query, read, send)."""

from __future__ import annotations

from pathlib import Path

from tether import SandboxPolicy, SkillLoader, SQLiteStore
from tether.tools.agent import make_agent_tool


async def test_agent_tool_subcommands(tmp_path: Path) -> None:
    """Verify agent spawn, status, wait, query, read, and send subcommands."""
    store = SQLiteStore(db_path=tmp_path / "tether.db")
    parent = store.create_session("Parent")
    sk_dir = tmp_path / "skills"
    sk_dir.mkdir()
    (sk_dir / "researcher.md").write_text(
        "---\nname: researcher\nmodel: ollama/qwen3.5:9b\n"
        "tools: [web]\nverify: [echo ok]\n---\nBody",
        encoding="utf-8",
    )
    loader = SkillLoader(search_dirs=[sk_dir])
    spawned: list[str] = []

    aspec = make_agent_tool(
        store=store,
        parent_session_id=parent.id,
        default_model="ollama/qwen3.5:9b",
        parent_sandbox=SandboxPolicy(workspace_root=tmp_path),
        skill_loader=loader,
        worker_spawner=lambda sid: (spawned.append(sid), 123)[1],
        wait_timeout=0.1,
    )
    assert "Usage: agent" in await aspec.invoke(["--help"])
    assert "Error: missing `<goal>`" in await aspec.invoke(["spawn"])
    assert "Error: skill `nope` not found" in await aspec.invoke(
        ["spawn", "--skill", "nope", "goal"]
    )
    assert "No child sub-agent" in await aspec.invoke(["query", "--all", "test"])

    cid = await aspec.invoke(
        [
            "spawn",
            "--skill",
            "researcher",
            "--model",
            "ollama/gemma4:e4b",
            "--tools",
            "web,mem",
            "SubGoal",
        ]
    )
    assert cid in spawned
    cid2 = await aspec.invoke(["spawn", "--skill", "researcher", "SubGoal2"])
    assert cid2.startswith("ses_")

    assert "Error: missing `<session_id>`" in await aspec.invoke(["status"])
    assert "not found" in await aspec.invoke(["status", "ses_missing"])
    assert "[PENDING]" in await aspec.invoke(["status", cid])

    assert "Error: specify one or more" in await aspec.invoke(["wait"])
    wait_out = await aspec.invoke(["wait", cid])
    assert cid in wait_out

    store.update_session(cid2, status="WAITING_INPUT", result="Need API key format?")
    wait_waiting = await aspec.invoke(["wait", cid2])
    assert "WAITING_INPUT" in wait_waiting and "waiting for input" in wait_waiting
    assert "resumed session" in await aspec.invoke(["send", cid2, "Use Bearer token"])

    store.update_session(cid2, status="COMPLETED", result="Child 2 finished")
    wait_done = await aspec.invoke(["wait", cid2])
    assert "COMPLETED" in wait_done

    assert "Error: usage" in await aspec.invoke(["query"])
    assert "expects an integer" in await aspec.invoke(["query", cid, "q", "--top", "bad"])
    assert "Error: missing `<query>`" in await aspec.invoke(["query", cid])
    assert "No BM25 RAG chunks" in await aspec.invoke(["query", cid, "nothing_matches"])

    assert "Error: missing `<session_id>`" in await aspec.invoke(["read"])
    assert "not found" in await aspec.invoke(["read", "ses_missing"])
    assert cid in await aspec.invoke(["read", cid])
    assert "no final result yet" in await aspec.invoke(["read", cid, "--full"])

    assert "Error: missing `<session_id>`" in await aspec.invoke(["send"])
    assert "Error: missing `<message>`" in await aspec.invoke(["send", cid])
    assert "not found" in await aspec.invoke(["send", "ses_missing", "hi"])
    assert "resumed session" in await aspec.invoke(["send", cid, "follow up"])
    store.update_session(cid, status="RUNNING")
    assert "running session" in await aspec.invoke(["send", cid, "live msg"])
    assert "Error: unknown subcommand" in await aspec.invoke(["bogus"])
