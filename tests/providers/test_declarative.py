from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

from tether.providers import (
    AnthropicProvider,
    OllamaProvider,
    OpenAIProvider,
    resolve_provider,
)
from tether.providers.base import ModelResponse
from tether.providers.declarative import (
    CommandProvider,
    build_declared,
    load_declared,
    providers_path,
)


def _write(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, text: str) -> Path:
    path = tmp_path / "p.yaml"
    path.write_text(text, encoding="utf-8")
    monkeypatch.setenv("TETHER_PROVIDERS", str(path))
    return path


def test_providers_path_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("TETHER_PROVIDERS", str(tmp_path / "x.yaml"))
    assert providers_path() == tmp_path / "x.yaml"


def test_providers_path_default(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("TETHER_PROVIDERS", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert providers_path() == tmp_path / ".tether" / "providers.yaml"


def test_missing_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("TETHER_PROVIDERS", str(tmp_path / "nope.yaml"))
    assert load_declared() == {}


def test_empty_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _write(monkeypatch, tmp_path, "")
    assert load_declared() == {}


def test_top_level_not_mapping(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _write(monkeypatch, tmp_path, "- a\n- b\n")
    with pytest.raises(ValueError, match="providers.yaml"):
        load_declared()


def test_entry_not_mapping(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _write(monkeypatch, tmp_path, "foo: bar\n")
    with pytest.raises(ValueError, match="providers.yaml"):
        load_declared()


def test_command_kind_minimal_loads(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _write(monkeypatch, tmp_path, "foo:\n  kind: command\n  argv: [x]\n  reply: r\n")
    assert load_declared()["foo"]["kind"] == "command"


def test_unknown_kind(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _write(monkeypatch, tmp_path, "foo:\n  kind: bogus\n")
    with pytest.raises(ValueError, match="openai, ollama, anthropic"):
        load_declared()


def test_missing_kind(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _write(monkeypatch, tmp_path, "foo:\n  base_url: http://x\n")
    with pytest.raises(ValueError, match="unknown kind"):
        load_declared()


@pytest.mark.parametrize("name", ["ollama", "openai", "anthropic"])
def test_cannot_shadow_builtins(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, name: str) -> None:
    _write(monkeypatch, tmp_path, f"{name}:\n  kind: openai\n")
    with pytest.raises(ValueError, match="shadow"):
        load_declared()


def test_build_openai_with_api_key_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MY_KEY", "secret")
    cfg = {"kind": "openai", "base_url": "http://x/v1", "api_key_env": "MY_KEY"}
    provider = build_declared(cfg, "m", num_ctx=1024)
    assert isinstance(provider, OpenAIProvider)
    assert provider.api_key == "secret"
    assert provider.base_url.startswith("http://x/v1")


def test_build_ollama(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = {"kind": "ollama", "host": "http://h:11434"}
    provider = build_declared(cfg, "m", num_ctx=1024)
    assert isinstance(provider, OllamaProvider)


def test_build_anthropic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("A_KEY", "ak")
    cfg = {"kind": "anthropic", "api_key_env": "A_KEY", "base_url": "http://a"}
    provider = build_declared(cfg, "m", num_ctx=1024)
    assert isinstance(provider, AnthropicProvider)
    assert provider.api_key == "ak"


def test_resolve_provider_declared(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _write(
        monkeypatch,
        tmp_path,
        "mygroq:\n  kind: openai\n  base_url: http://groq.local/v1\n",
    )
    provider = resolve_provider("mygroq/llama")
    assert isinstance(provider, OpenAIProvider)
    assert provider.model_name == "llama"
    assert provider.base_url.startswith("http://groq.local/v1")


def test_resolve_provider_unknown_still_raises(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _write(monkeypatch, tmp_path, "mygroq:\n  kind: openai\n")
    with pytest.raises(ValueError, match="Unknown model provider"):
        resolve_provider("other/llama")


def _script(code: str, *extra: str) -> list[str]:
    return [sys.executable, "-c", code, *extra]


def _run(provider: CommandProvider, messages: list[dict[str, str]] | None = None) -> ModelResponse:
    msgs: list[dict[str, str]] = messages or [{"role": "user", "content": "hi"}]
    return asyncio.run(provider.generate(msgs, []))  # type: ignore[arg-type]


def test_claude_cannot_be_shadowed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _write(monkeypatch, tmp_path, "claude:\n  kind: openai\n")
    with pytest.raises(ValueError, match="cannot shadow"):
        load_declared()


def test_command_success_with_usage() -> None:
    code = (
        "import json;"
        "print(json.dumps({'r': json.dumps({'cmd': 'ls'}),"
        " 'u': {'a': 1, 'b': 2, 'c': 5, 'bad': True}}))"
    )
    provider = CommandProvider(
        "m",
        argv=_script(code),
        reply="r",
        usage={"prompt": ["u.a", "u.b", "u.bad", "u.none"], "completion": "u.c"},
    )
    assert provider.structured_history is False
    resp = _run(provider)
    assert resp.action is not None
    assert resp.action.cmd == "ls"
    assert resp.prompt_tokens == 3
    assert resp.completion_tokens == 5


def test_command_usage_prompt_string_and_no_completion() -> None:
    code = "import json; print(json.dumps({'r': 'plain', 'n': 7}))"
    provider = CommandProvider("m", argv=_script(code), reply="r", usage={"prompt": "n"})
    resp = _run(provider)
    assert resp.content == "plain"
    assert resp.action is None
    assert resp.prompt_tokens == 7
    assert resp.completion_tokens == 0


def test_command_xml_reply() -> None:
    text = '<parameter name="cmd">echo hi</parameter><parameter name="stdin">body</parameter>'
    code = f"import json; print(json.dumps({{'r': {text!r}}}))"
    resp = _run(CommandProvider("m", argv=_script(code), reply="r"))
    assert resp.action is not None
    assert resp.action.cmd == "echo hi"
    assert resp.action.stdin == "body"


def test_command_xml_reply_without_stdin() -> None:
    text = '<parameter name="cmd">pwd</parameter>'
    code = f"import json; print(json.dumps({{'r': {text!r}}}))"
    resp = _run(CommandProvider("m", argv=_script(code), reply="r"))
    assert resp.action is not None
    assert resp.action.cmd == "pwd"
    assert resp.action.stdin is None


def test_command_missing_reply_path() -> None:
    code = "import json; print(json.dumps({'x': 1}))"
    resp = _run(CommandProvider("m", argv=_script(code), reply="a.b"))
    assert resp.content == ""
    assert resp.action is None
    assert resp.prompt_tokens == 0


def test_command_nonzero_exit() -> None:
    code = "import sys; sys.stderr.write('boom'); sys.exit(3)"
    with pytest.raises(RuntimeError, match="boom"):
        _run(CommandProvider("m", argv=_script(code), reply="r"))


def test_command_invalid_json() -> None:
    code = "print('not json')"
    with pytest.raises(RuntimeError, match="invalid JSON: not json"):
        _run(CommandProvider("m", argv=_script(code), reply="r"))


def test_command_timeout() -> None:
    code = "import time; time.sleep(5)"
    with pytest.raises(RuntimeError, match="timed out"):
        _run(CommandProvider("m", argv=_script(code), reply="r", timeout=0.2))


_ECHO = (
    "import sys, json;"
    "print(json.dumps({'r': json.dumps({'model': sys.argv[1], 'system': sys.argv[2],"
    " 'stdin': sys.stdin.read()})}))"
)


def test_command_placeholders_default_stdin() -> None:
    provider = CommandProvider("mymodel", argv=_script(_ECHO, "{model}", "{system}"), reply="r")
    resp = _run(
        provider,
        [
            {"role": "system", "content": "S1"},
            {"role": "system", "content": "S2"},
            {"role": "user", "content": "hello {model}"},
            {"role": "assistant", "content": "yo"},
        ],
    )
    data = json.loads(resp.content)
    assert data["model"] == "mymodel"
    assert data["system"].startswith("S1\nS2\n\nReply with ONLY one JSON object")
    assert data["system"].endswith('"<optional multiline payload or null>"}')
    assert data["stdin"] == "[user]\nhello {model}\n\n[assistant]\nyo"


def test_command_placeholders_custom_stdin() -> None:
    provider = CommandProvider(
        "mm",
        argv=_script(_ECHO, "x", "y"),
        reply="r",
        stdin="{model}|{system}|{conversation}",
    )
    resp = _run(provider, [{"role": "system", "content": "S"}, {"role": "user", "content": "u"}])
    stdin = json.loads(resp.content)["stdin"]
    assert stdin.startswith("mm|S\n\nReply with ONLY")
    assert stdin.endswith("|[user]\nu")


def test_build_command_and_load(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _write(
        monkeypatch,
        tmp_path,
        "cli:\n  kind: command\n  argv: [echo, '{model}']\n  reply: out.text\n"
        "  stdin: '{conversation}'\n  timeout: 5\n"
        "  usage:\n    prompt: [u.a, u.b]\n    completion: u.c\n",
    )
    cfg = load_declared()["cli"]
    provider = build_declared(cfg, "m", num_ctx=1024)
    assert isinstance(provider, CommandProvider)
    assert provider.timeout == 5


def test_build_command_defaults() -> None:
    provider = build_declared({"kind": "command", "argv": ["x"], "reply": "r"}, "m", num_ctx=1024)
    assert isinstance(provider, CommandProvider)
    assert provider.timeout == 300
    assert provider.stdin == "{conversation}"


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ("reply: r\n", "requires `argv`"),
        ("argv: []\n  reply: r\n", "requires `argv`"),
        ("argv: [1]\n  reply: r\n", "requires `argv`"),
        ("argv: [x]\n", "requires `reply`"),
        ("argv: [x]\n  reply: 3\n", "requires `reply`"),
        ("argv: [x]\n  reply: r\n  stdin: 3\n", "invalid `stdin`"),
        ("argv: [x]\n  reply: r\n  timeout: abc\n", "invalid `timeout`"),
        ("argv: [x]\n  reply: r\n  timeout: true\n", "invalid `timeout`"),
        ("argv: [x]\n  reply: r\n  timeout: -1\n", "invalid `timeout`"),
        ("argv: [x]\n  reply: r\n  usage: 3\n", "invalid `usage`"),
        ("argv: [x]\n  reply: r\n  usage:\n    prompt: 3\n", "invalid `usage.prompt`"),
        ("argv: [x]\n  reply: r\n  usage:\n    completion: [a]\n", "invalid `usage.completion`"),
    ],
)
def test_command_validation_errors(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, body: str, message: str
) -> None:
    _write(monkeypatch, tmp_path, f"cli:\n  kind: command\n  {body}")
    with pytest.raises(ValueError, match=f"providers.yaml: entry `cli`.*{message}"):
        load_declared()


def test_command_custom_dialect_end_to_end() -> None:
    from tether.providers.declarative import _build_dialects

    text = "RUN[ls -la]WITH[body]"
    code = f"import json; print(json.dumps({{'r': {text!r}}}))"
    dialects = _build_dialects([{"regex": r"RUN\[(?P<cmd>.*?)\]WITH\[(?P<stdin>.*?)\]"}])
    resp = _run(CommandProvider("m", argv=_script(code), reply="r", dialects=dialects))
    assert resp.action is not None
    assert resp.action.cmd == "ls -la"
    assert resp.action.stdin == "body"


def test_command_custom_dialect_no_match_and_empty_cmd() -> None:
    from tether.providers.declarative import _build_dialects

    dialects = _build_dialects([{"regex": r"RUN\[(?P<cmd>.*?)\]"}])
    assert dialects[0]("nothing here") is None
    assert dialects[0]("RUN[   ]") is None
    call = dialects[0]("RUN[ pwd ]")
    assert call is not None
    assert call.cmd == "pwd"
    assert call.stdin is None


@pytest.mark.parametrize(
    ("dialects", "message"),
    [
        ("dialects: nope", "invalid `dialects`"),
        ("dialects: [1]", "`regex` required"),
        ("dialects: [{foo: bar}]", "`regex` required"),
        ("dialects: [{regex: '('}]", "invalid `dialects` regex"),
        ("dialects: [{regex: 'abc'}]", "named group `cmd`"),
    ],
)
def test_command_dialects_validation_errors(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, dialects: str, message: str
) -> None:
    _write(
        monkeypatch,
        tmp_path,
        f"cli:\n  kind: command\n  argv: [echo]\n  reply: r\n  {dialects}\n",
    )
    with pytest.raises(ValueError, match=f"providers.yaml: entry `cli`.*{message}"):
        load_declared()
