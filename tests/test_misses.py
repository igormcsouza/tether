"""`tether misses`: unparsed model replies as fixture-ready JSONL (#53)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tether import ActionCall, ModelResponse, register_provider
from tether.cli import _async_main
from tether.store import SQLiteStore


class Prose:
    model_name = "x"

    def __init__(self, text: str) -> None:
        self.text = text
        self.i = 0

    async def generate(self, messages: Any, tools: Any) -> ModelResponse:
        self.i += 1
        return ModelResponse(
            content=f"{self.text} #{self.i}", action=None, prompt_tokens=1, completion_tokens=1
        )


class Done:
    model_name = "x"

    async def generate(self, messages: Any, tools: Any) -> ModelResponse:
        return ModelResponse(
            content="",
            action=ActionCall(cmd="done", stdin="ok"),
            prompt_tokens=1,
            completion_tokens=1,
        )


async def _run(capsys: pytest.CaptureFixture[str], argv: list[str]) -> tuple[int, str, str]:
    code = await _async_main(argv)
    cap = capsys.readouterr()
    return code, cap.out, cap.err


async def _session(capsys: pytest.CaptureFixture[str], db: str, prefix: str, provider: Any) -> str:
    register_provider(prefix, lambda name: provider)
    argv = ["run", "--json", "--model", f"{prefix}/m", "--db", db, "--max-steps", "3", "g"]
    _, out, _ = await _run(capsys, argv)
    return str(json.loads(out)["id"])


async def test_misses_outputs_and_filters(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db = str(tmp_path / "t.db")
    s1 = await _session(capsys, db, "miss-a", Prose("a" * 500))
    s2 = await _session(capsys, db, "miss-b", Prose("b"))

    code, out, _ = await _run(capsys, ["misses", "--db", db])
    assert code == 0
    assert f"[{s1} step" in out and "miss-a/m]" in out
    assert "a" * 300 in out and "a" * 301 not in out

    code, out, _ = await _run(capsys, ["misses", "--json", "--db", db])
    rows = [json.loads(line) for line in out.splitlines()]
    assert code == 0 and len(rows) >= 2
    assert {r["session"] for r in rows} == {s1, s2}
    assert all(r["expected"] is None and r["reply"] and "step" in r for r in rows)
    assert any(len(r["reply"]) > 300 for r in rows)

    _, out, _ = await _run(capsys, ["misses", "--json", "--limit", "1", "--db", db])
    assert len(out.splitlines()) == 1

    _, out, _ = await _run(capsys, ["misses", "--json", "--model", "miss-b/m", "--db", db])
    assert {json.loads(x)["session"] for x in out.splitlines()} == {s2}

    _, out, _ = await _run(capsys, ["misses", s1, "--json", "--db", db])
    assert {json.loads(x)["session"] for x in out.splitlines()} == {s1}

    code, _, err = await _run(capsys, ["misses", "ses_nope", "--db", db])
    assert code == 1 and "session `ses_nope` not found." in err


async def test_misses_empty(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db = str(tmp_path / "t.db")
    await _session(capsys, db, "miss-ok", Done())
    code, out, _ = await _run(capsys, ["misses", "--db", db])
    assert code == 0 and out.strip() == "No unparsed replies."
    code, out, _ = await _run(capsys, ["misses", "--json", "--db", db])
    assert code == 0 and out == ""


async def test_store_list_nudges(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db = str(tmp_path / "t.db")
    s1 = await _session(capsys, db, "miss-c", Prose("c"))
    store = SQLiteStore(db_path=db)
    rows = store.list_nudges()
    assert len(rows) >= 2
    assert all(t.event_type == "nudge" and s.id == s1 for s, t in rows)
    ids = [t.id for _, t in rows]
    assert ids == sorted(ids, reverse=True)
    assert len(store.list_nudges(limit=1)) == 1
    assert store.list_nudges(session_id="nope") == []
    assert store.list_nudges(model="other/m") == []
    assert len(store.list_nudges(session_id=s1, model="miss-c/m")) == len(rows)
