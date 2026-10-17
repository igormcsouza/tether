"""Unit tests for tether/tools/mem.py (pin, unpin, list, BM25 FTS5 search, recall)."""

from __future__ import annotations

from pathlib import Path

from tether import Harness, SandboxPolicy, SQLiteStore


async def test_mem_tool(tmp_path: Path) -> None:
    """Verify mem pin, unpin, list, search (BM25 FTS5), and recall subcommands."""
    db_file = tmp_path / "tether.db"
    store = SQLiteStore(db_path=db_file)
    srec = store.create_session("Mem test")
    sandbox = SandboxPolicy(workspace_root=tmp_path, use_kernel_sandbox=False)
    harness = Harness(db_path=db_file, tools=["mem"], sandbox=sandbox)
    mux = harness.build_multiplexer(srec.id, ["mem"], sandbox, srec.model)

    assert "Usage: mem" in (await mux.execute("mem --help")).output
    assert "No pinned facts." in (await mux.execute("mem list")).output
    assert "Error: missing `<key>`" in (await mux.execute("mem pin")).output
    assert "Error: missing `<val>`" in (await mux.execute("mem pin k1")).output
    assert "Pinned `k1`" in (await mux.execute("mem pin k1", stdin="v1")).output
    assert "k1: v1" in (await mux.execute("mem list")).output
    assert "Error: missing `<key>`" in (await mux.execute("mem unpin")).output
    assert "Unpinned `k1`" in (await mux.execute("mem unpin k1")).output
    assert "not found" in (await mux.execute("mem unpin k1")).output

    obs = store.add_observation(srec.id, 1, "web search", "Quantum computing breakthroughs 2026")
    assert "Error: missing `<query>`" in (await mux.execute("mem search")).output
    assert "expects an integer" in (await mux.execute("mem search q --top bad")).output
    assert "Quantum" in (await mux.execute(f"mem search Quantum --obs {obs.id} --top 2")).output
    assert "No matching chunks" in (await mux.execute("mem search nonexistent_xyz")).output

    assert "Error: missing `<obs_id>`" in (await mux.execute("mem recall")).output
    assert "not found" in (await mux.execute("mem recall obs_999")).output
    assert "Quantum" in (await mux.execute(f"mem recall {obs.id}")).output
    assert "Error: unknown subcommand" in (await mux.execute("mem bogus")).output
