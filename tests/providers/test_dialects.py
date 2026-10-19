"""Table-driven tests for tool-call dialect extractors."""

import json
from pathlib import Path

import pytest

from tether.providers import base
from tether.providers.base import ActionCall, extract_fallback_action, register_dialect

FIXTURE = Path(__file__).parent.parent / "fixtures" / "dialects.jsonl"
ROWS = [json.loads(line) for line in FIXTURE.read_text().splitlines() if line.strip()]


@pytest.mark.parametrize("row", ROWS, ids=[str(i) for i in range(len(ROWS))])
def test_dialect_fixture_rows(row: dict) -> None:
    call = extract_fallback_action(row["reply"])
    if row["cmd"] is None:
        assert call is None
    else:
        assert call is not None
        assert call.cmd == row["cmd"]
        assert call.stdin == row["stdin"]


def test_fixture_covers_required_forms() -> None:
    assert len(ROWS) >= 6
    assert any(r["cmd"] is None for r in ROWS)


def test_empty_text_returns_none() -> None:
    assert extract_fallback_action("") is None


def test_parameter_tags_empty_cmd_is_none() -> None:
    text = '<parameter name="cmd">   </parameter>'
    assert extract_fallback_action(text) is None


def test_register_dialect_appends_and_is_used() -> None:
    def custom(text: str) -> ActionCall | None:
        if text.startswith("RUN:"):
            return ActionCall(cmd=text[4:].strip(), stdin=None)
        return None

    before = list(base.DIALECTS)
    try:
        assert register_dialect(custom) is custom
        assert base.DIALECTS[-1] is custom
        call = extract_fallback_action("RUN: ls")
        assert call is not None
        assert call.cmd == "ls"
    finally:
        base.DIALECTS.remove(custom)
    assert base.DIALECTS == before
    assert extract_fallback_action("RUN: ls") is None


def test_extra_extractors_tried_after_builtins() -> None:
    def custom(text: str) -> ActionCall | None:
        return ActionCall(cmd="extra", stdin=None) if "zzz" in text else None

    call = extract_fallback_action("zzz", extra=[custom])
    assert call is not None
    assert call.cmd == "extra"
    assert extract_fallback_action("zzz") is None
    builtin = extract_fallback_action('{"cmd": "ls"} zzz', extra=[custom])
    assert builtin is not None
    assert builtin.cmd == "ls"


def test_tool_call_block_with_non_object_payload_is_ignored() -> None:
    assert extract_fallback_action("<tool_call>[1, 2]</tool_call>") is None


def test_act_ast_rejects_non_call_expression() -> None:
    from tether.providers.base import _act_from_ast

    assert _act_from_ast(") or (1") is None
