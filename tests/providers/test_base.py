"""Unit tests for tether/providers/__init__.py and tether/providers/base.py."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tether import Harness, ModelResponse, extract_fallback_action, register_provider
from tether.providers import (
    AnthropicProvider,
    OllamaProvider,
    OpenAIProvider,
    parse_tool_arguments,
    resolve_provider,
)


def test_fallback_9b_action_extractor_and_argument_parser() -> None:
    """Verify fallback extraction for Qwen <tool_call> XML, inline act(...), and AST parser."""
    xml_text = (
        "I will search now.\n"
        "<tool_call>\n"
        '{"name": "act", "arguments": {"cmd": "web search \\"AI news\\""}}\n'
        "</tool_call>"
    )
    call1 = extract_fallback_action(xml_text)
    assert call1 is not None
    assert call1.cmd == 'web search "AI news"'

    py_text = 'Thought: finished.\nact("done", stdin="Final report ready")'
    call2 = extract_fallback_action(py_text)
    assert call2 is not None
    assert call2.cmd == "done"
    assert call2.stdin == "Final report ready"

    multiline_text = 'act("done", stdin="# Summary\n\n- Item 1 (with parens)\n- Item 2")'
    call3 = extract_fallback_action(multiline_text)
    assert call3 is not None
    assert call3.cmd == "done"
    assert call3.stdin == "# Summary\n\n- Item 1 (with parens)\n- Item 2"

    assert parse_tool_arguments("not json") is None
    assert parse_tool_arguments("[1, 2, 3]") is None
    assert parse_tool_arguments({"other": 1}) is None
    c_cmd = parse_tool_arguments({"command": "web search ai", "stdin": " body "})
    assert c_cmd is not None and c_cmd.cmd == "web search ai"

    assert extract_fallback_action("") is None
    assert extract_fallback_action("<tool_call>not json</tool_call>") is None
    assert extract_fallback_action('Here is JSON: {"cmd": "done", "stdin": "raw_json"}') is not None
    assert extract_fallback_action('{"cmd": ""}') is None

    ast1 = extract_fallback_action("act(cmd='done', stdin='via_kw')")
    assert ast1 is not None and ast1.cmd == "done" and ast1.stdin == "via_kw"
    ast2 = extract_fallback_action("act('done', 'pos_stdin')")
    assert ast2 is not None and ast2.cmd == "done" and ast2.stdin == "pos_stdin"
    ast3 = extract_fallback_action("act(command='done')")
    assert ast3 is not None and ast3.cmd == "done"
    ast_mismatched1 = extract_fallback_action("""act(("done"), ("ast_pos_stdin"))""")
    assert ast_mismatched1 is not None and ast_mismatched1.stdin == "ast_pos_stdin"
    ast_mismatched2 = extract_fallback_action("""act(stdin="ast_kw_stdin", command='done')""")
    assert ast_mismatched2 is not None and ast_mismatched2.cmd == "done"
    assert extract_fallback_action("act(invalid syntax ===)") is None
    assert extract_fallback_action("no action here") is None


async def test_provider_registry_and_custom_sdk_routing(tmp_path: Path) -> None:
    """Verify resolve_provider routing and custom SDK provider registration."""
    assert isinstance(resolve_provider("qwen3.5:9b"), OllamaProvider)
    assert isinstance(resolve_provider("openai/gpt-4o-mini"), OpenAIProvider)
    assert isinstance(resolve_provider("anthropic/claude-3-7-sonnet-latest"), AnthropicProvider)
    with pytest.raises(ValueError, match="Provider prefix cannot be empty"):
        register_provider("  / ", lambda m: OllamaProvider(m))
    with pytest.raises(ValueError, match="Unknown model provider"):
        resolve_provider("unknown_vendor/model")

    class CustomGatewayProvider:
        def __init__(self, model_name: str) -> None:
            self.model_name = model_name

        async def generate(
            self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
        ) -> ModelResponse:
            raw_out = f'act("done", stdin="Routed via custom gateway: {self.model_name}")'
            return ModelResponse(
                content=raw_out,
                action=extract_fallback_action(raw_out),
                prompt_tokens=320,
            )

    register_provider("gateway", lambda name: CustomGatewayProvider(name))
    harness = Harness(
        db_path=tmp_path / "tether.db",
        model="gateway/qwen-enterprise-32b",
    )
    session = await harness.run("Test custom provider")
    assert session.status == "COMPLETED"
    assert session.result == "Routed via custom gateway: qwen-enterprise-32b"
    assert session.peak_tokens == 320
