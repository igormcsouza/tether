"""Tests for the `web` domain allowlist (#124 item 5). Fakes only, no network."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from tests.conftest import FakeScriptedProvider
from tether import SandboxPolicy
from tether.tools.web import make_web_tool


@pytest.fixture(autouse=True)
def _no_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    """Never touch DNS: allowed hosts count as public without a lookup."""
    monkeypatch.setenv("TETHER_WEB_ALLOW_PRIVATE", "1")


def _install_transport(monkeypatch: pytest.MonkeyPatch, handler: Any) -> list[str]:
    """Route httpx clients through a MockTransport; return the hosts actually contacted."""
    seen: list[str] = []

    def recording(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.host)
        return handler(request)

    orig = httpx.AsyncClient

    def patched(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = httpx.MockTransport(recording)
        return orig(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", patched)
    return seen


def _ok(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, headers={"content-type": "text/plain"}, text="ok")


async def test_allowed_and_blocked_hosts(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _install_transport(monkeypatch, _ok)
    tool = make_web_tool(web_allow=("python.org",))

    assert await tool.invoke(["fetch", "https://docs.python.org/x"]) == "ok"
    assert await tool.invoke(["fetch", "https://python.org/"]) == "ok"
    blocked = await tool.invoke(["fetch", "https://evil.com/"])
    assert blocked.startswith("Error:")
    assert "Instead:" in blocked
    assert "python.org" in blocked
    assert "evil.com" not in seen


async def test_redirect_to_blocked_host_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "docs.python.org":
            return httpx.Response(302, headers={"location": "https://evil.com/steal"})
        return httpx.Response(200, text="SHOULD-NOT-SERVE")

    seen = _install_transport(monkeypatch, handler)
    tool = make_web_tool(web_allow=("python.org",))
    result = await tool.invoke(["fetch", "https://docs.python.org/start"])

    assert result.startswith("Error:")
    assert "blocked" in result
    assert "evil.com" not in seen
    assert "SHOULD-NOT-SERVE" not in result


@pytest.mark.parametrize(
    "url",
    [
        "https://python.org.evil.com/",
        "https://evilpython.org/",
        "https://python.org@evil.com/",
        "http://93.184.216.34/",
        "http://[2606:4700::1111]/",
        "http://127.0.0.1/",
    ],
)
async def test_lookalike_and_ip_hosts_refused(monkeypatch: pytest.MonkeyPatch, url: str) -> None:
    seen = _install_transport(monkeypatch, _ok)
    tool = make_web_tool(web_allow=("python.org",))

    result = await tool.invoke(["fetch", url])
    assert result.startswith("Error:")
    assert "Instead:" in result
    assert seen == []


async def test_wildcard_matches_subdomains_only(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _install_transport(monkeypatch, _ok)
    tool = make_web_tool(web_allow=("*.python.org",))

    assert await tool.invoke(["fetch", "https://docs.python.org/x"]) == "ok"
    apex = await tool.invoke(["fetch", "https://python.org/"])
    assert apex.startswith("Error:")
    assert "Instead:" in apex
    assert seen == ["docs.python.org"]


async def test_empty_allowlist_denies_everything(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _install_transport(monkeypatch, _ok)
    tool = make_web_tool(web_allow=())

    assert (await tool.invoke(["fetch", "https://python.org/"])).startswith("Error:")
    assert seen == []


async def test_search_filters_off_list_results(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("SEARXNG_URL", "BRAVE_API_KEY", "TAVILY_API_KEY"):
        monkeypatch.delenv(var, raising=False)

    def handler(request: httpx.Request) -> httpx.Response:
        link = "https://duckduckgo.com/l/?uddg=https%3A%2F%2Fevil.com%2F"
        return httpx.Response(200, text=f'<a class="result__a" href="{link}"><b>Evil</b></a>')

    _install_transport(monkeypatch, handler)
    tool = make_web_tool(web_allow=("python.org",))
    result = await tool.invoke(["search", "python"])

    assert "evil.com" not in result
    assert "Instead:" in result


async def test_ssrf_guard_still_applies(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TETHER_WEB_ALLOW_PRIVATE", raising=False)
    seen = _install_transport(monkeypatch, _ok)

    for allow in (None, ("localhost",)):
        result = await make_web_tool(web_allow=allow).invoke(["fetch", "http://localhost/"])
        assert result.startswith("Error:")
        assert "non-public" in result

    metadata_tool = make_web_tool(web_allow=None)
    metadata = await metadata_tool.invoke(["fetch", "http://169.254.169.254/latest"])
    assert "non-public" in metadata
    assert seen == []


def test_children_only_narrow() -> None:
    parent = SandboxPolicy(web_allow=("python.org",))
    assert parent.attenuate(child_web_allow=("evil.com",)).web_allow == ()
    assert parent.attenuate(child_web_allow=("docs.python.org",)).web_allow == ("docs.python.org",)
    assert parent.attenuate().web_allow == ("python.org",)
    assert parent.attenuate(child_web_allow=None).web_allow == ("python.org",)
    assert SandboxPolicy().attenuate(child_web_allow=("x.org",)).web_allow == ("x.org",)

    restored = SandboxPolicy.from_dict(parent.to_dict())
    assert restored.web_allow == ("python.org",)
    legacy = parent.to_dict()
    legacy.pop("web_allow")
    assert SandboxPolicy.from_dict(legacy).web_allow is None


def test_web_allow_normalised_and_validated() -> None:
    policy = SandboxPolicy(web_allow=("PYTHON.org.", "*.Example.com"))
    assert policy.web_allow == ("python.org", "*.example.com")
    assert SandboxPolicy().web_allow is None
    for bad in ("https://python.org", "python.org/x", "python.org:443", "u@python.org", "*", ""):
        with pytest.raises(ValueError):
            SandboxPolicy(web_allow=(bad,))


def test_cli_web_allow_flag() -> None:
    from tether import cli

    ns = cli.build_parser().parse_args(["run", "--web-allow", "python.org", "task"])
    assert ns.web_allow == "python.org"
    assert cli.main(["run", "--web-allow", "", "task"]) == cli.EXIT_USAGE


def test_mcp_web_allow_in_schema() -> None:
    from tether import mcp

    assert "web_allow" in json.dumps(mcp.TOOLS)


class _Stop(Exception):
    pass


async def test_harness_built_web_tool_refuses_off_list_host(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tether import harness as harness_mod
    from tether.harness import Harness

    built: list[Any] = []
    real = harness_mod.make_web_tool

    def spy(*args: Any, **kwargs: Any) -> Any:
        tool = real(*args, **kwargs)
        built.append(tool)
        return tool

    monkeypatch.setattr(harness_mod, "make_web_tool", spy)
    monkeypatch.setattr(harness_mod, "resolve_provider", lambda *a, **k: FakeScriptedProvider([]))
    sandbox = SandboxPolicy(web_allow=("python.org",))
    h = Harness(model="m", sandbox=sandbox, db_path=tmp_path / "t.db")
    h.build_multiplexer("sid", ["web"], sandbox, "m")
    assert built, "web tool was not built"
    result = await built[0].invoke(["fetch", "https://evil.example/"])
    assert result.startswith("Error:")
    assert "not allowed" in result


async def test_cli_web_allow_reaches_sandbox_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tether import cli

    seen: list[Any] = []

    def fake(**kwargs: Any) -> None:
        seen.append(kwargs.get("web_allow"))
        raise _Stop

    monkeypatch.setattr(cli, "SandboxPolicy", fake)
    with pytest.raises(_Stop):
        await cli._async_main(["run", "--web-allow", "python.org,*.github.com", "task"])
    assert seen == [("python.org", "*.github.com")]


def test_mcp_run_builds_sandbox_with_parsed_web_allow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tether import mcp

    captured: dict[str, Any] = {}

    class FakeHarness:
        def __init__(self, **kwargs: Any) -> None:
            captured.update(kwargs)

        def spawn(self, goal: str) -> str:
            return "sid"

    monkeypatch.setattr(mcp, "Harness", FakeHarness)
    impl = mcp.TetherMCP(db_path=tmp_path / "t.db", workspace=tmp_path)
    out = asyncio.run(
        impl.call("tether_run", {"goal": "g", "wait": False, "web_allow": "python.org"})
    )
    assert out["id"] == "sid"
    assert captured["sandbox"].web_allow == ("python.org",)
