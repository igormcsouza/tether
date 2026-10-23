"""Per-call model params: yaml < SDK/CLI/MCP, request routing per provider, persistence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from tether import Harness
from tether.cli import _async_main
from tether.providers import resolve_provider
from tether.providers.anthropic import AnthropicProvider
from tether.providers.declarative import build_declared, load_declared
from tether.providers.ollama import OllamaProvider
from tether.providers.openai import OpenAIProvider
from tether.store import SQLiteStore


def _capture(reply: dict[str, Any]) -> tuple[httpx.AsyncClient, list[dict[str, Any]]]:
    seen: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json=reply)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler)), seen


async def test_openai_params_override_defaults() -> None:
    client, seen = _capture({"choices": [{"message": {"content": "hi"}}]})
    prov = OpenAIProvider("m", client=client, params={"temperature": 0, "reasoning_effort": "low"})
    await prov.generate([{"role": "user", "content": "x"}], [])
    assert seen[0]["temperature"] == 0 and seen[0]["reasoning_effort"] == "low"


async def test_anthropic_params_are_top_level() -> None:
    client, seen = _capture({"content": [{"type": "text", "text": "hi"}]})
    prov = AnthropicProvider("m", client=client, params={"max_tokens": 99, "temperature": 0})
    await prov.generate([{"role": "user", "content": "x"}], [])
    assert seen[0]["max_tokens"] == 99 and seen[0]["temperature"] == 0


async def test_ollama_params_split_request_keys_and_options() -> None:
    client, seen = _capture({"message": {"content": "hi"}})
    prov = OllamaProvider(
        "m", client=client, params={"think": False, "top_p": 0.5, "temperature": 0}
    )
    await prov.generate([{"role": "user", "content": "x"}], [])
    assert seen[0]["think"] is False
    assert seen[0]["options"] == {"num_ctx": 8192, "temperature": 0, "top_p": 0.5}


def test_yaml_params_sit_under_explicit_params(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = tmp_path / "p.yaml"
    path.write_text(
        "d:\n  kind: openai\n  base_url: http://x\n  params: {temperature: 0.5, top_p: 1}\n"
    )
    monkeypatch.setenv("TETHER_PROVIDERS", str(path))
    prov = resolve_provider("d/m", params={"temperature": 0})
    assert isinstance(prov, OpenAIProvider) and prov.params == {"temperature": 0, "top_p": 1}
    cfg = load_declared()["d"]
    plain = build_declared(cfg, "m", num_ctx=1)
    assert isinstance(plain, OpenAIProvider) and plain.params == {"temperature": 0.5, "top_p": 1}
    assert resolve_provider("openai/m", params={"a": 1}).params == {"a": 1}  # type: ignore[attr-defined]
    assert resolve_provider("anthropic/m", params={"a": 1}).params == {"a": 1}  # type: ignore[attr-defined]
    assert resolve_provider("ollama/m", params={"a": 1}).params == {"a": 1}  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    "entry",
    [
        "d:\n  kind: openai\n  params: [1]\n",
        "d:\n  kind: command\n  argv: [x]\n  reply: r\n  params: {a: 1}\n",
    ],
)
def test_invalid_params_in_yaml(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, entry: str
) -> None:
    path = tmp_path / "p.yaml"
    path.write_text(entry)
    monkeypatch.setenv("TETHER_PROVIDERS", str(path))
    with pytest.raises(ValueError, match="invalid `params`"):
        load_declared()


async def test_harness_params_are_stored_and_reach_the_provider(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from tests.conftest import FakeScriptedProvider
    from tether import harness as harness_mod

    seen: dict[str, Any] = {}

    def fake_resolve(model: str, **kw: Any) -> FakeScriptedProvider:
        seen.update(kw)
        return FakeScriptedProvider([])

    monkeypatch.setattr(harness_mod, "resolve_provider", fake_resolve)
    h = Harness(db_path=tmp_path / "t.db", params={"temperature": 0})
    rec = await h.run("g")
    assert seen["params"] == {"temperature": 0} and rec.sandbox_config["params"] == {
        "temperature": 0
    }
    plain = Harness(db_path=tmp_path / "t2.db")
    assert "params" not in (await plain.run("g")).sandbox_config and seen["params"] is None


async def test_cli_param_flag(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from tests.conftest import FakeScriptedProvider
    from tether import register_provider

    register_provider("params-cli", lambda name: FakeScriptedProvider([]))
    db = str(tmp_path / "t.db")
    argv = ["run", "--json", "--model", "params-cli/m", "--db", db]
    assert (
        await _async_main([*argv, "--param", "temperature=0", "--param", "think=false", "g"]) == 0
    )
    capsys.readouterr()
    stored = SQLiteStore(db).list_sessions()[0].sandbox_config["params"]
    assert stored == {"temperature": 0, "think": False}
    assert await _async_main([*argv, "--param", "oops", "g"]) == 1
    assert "KEY=VALUE" in capsys.readouterr().err
