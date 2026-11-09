"""Coverage for edge branches of the web allowlist (#124 item 5). No network."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from tether import SandboxPolicy, api
from tether.cli import _async_main
from tether.sandbox import parse_web_allow
from tether.tools.web import _filter_results_by_host, _render_results, host_allowed


def test_wildcard_parent_narrows_subdomain_child() -> None:
    parent = SandboxPolicy(web_allow=("*.python.org",))
    assert parent.attenuate(child_web_allow=("docs.python.org",)).web_allow == ("docs.python.org",)


def test_colon_host_that_is_not_an_ip_is_rejected() -> None:
    assert host_allowed("bad:host", ("bad:host",)) is False


def test_filter_results_keeps_allowed_hosts() -> None:
    items = [("t", "https://python.org/a", "s"), ("t2", "https://evil.com/b", "s2")]
    kept, blocked = _filter_results_by_host(items, ("python.org",))
    assert kept == [items[0]]
    assert blocked == 1


async def test_bad_web_allow_cli_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    code = await _async_main(["run", "--web-allow", "http://x", "g"])
    assert code == api.EXIT_USAGE
    assert "--web-allow" in capsys.readouterr().err


async def test_bad_web_allow_pipeline_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    code = await _async_main(["pipeline", "p.yaml", "g", "--web-allow", "http://x"])
    assert code == api.EXIT_USAGE
    assert "--web-allow" in capsys.readouterr().err


@pytest.mark.parametrize("bad", ["py thon.org", "*.*.org", "a*b.org", "*org"])
def test_parse_web_allow_rejects_bad_patterns(bad: str) -> None:
    with pytest.raises(ValueError):
        parse_web_allow((bad,))


def test_parse_web_allow_accepts_leading_wildcard() -> None:
    assert parse_web_allow(("*.python.org",)) == ("*.python.org",)


def test_mcp_bad_web_allow_is_tool_error(tmp_path: Path) -> None:
    from tether import mcp

    impl = mcp.TetherMCP(db_path=tmp_path / "t.db", workspace=tmp_path)
    with pytest.raises(Exception) as info:
        asyncio.run(impl.call("tether_run", {"goal": "g", "wait": False, "web_allow": "http://x"}))
    assert type(info.value).__name__ == "ToolError"
    assert "web_allow" in str(info.value)


async def test_pipeline_bad_web_allow_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    code = await _async_main(["pipeline", "--web-allow", "http://x", "p.yaml", "g"])
    assert code == api.EXIT_USAGE
    assert "Error: --web-allow:" in capsys.readouterr().err


async def test_pipeline_web_allow_reaches_sandbox_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    from tether import cli

    class _Stop(Exception):
        pass

    seen: list[object] = []

    def fake(**kwargs: object) -> None:
        seen.append(kwargs.get("web_allow"))
        raise _Stop

    monkeypatch.setattr(cli, "SandboxPolicy", fake)
    with pytest.raises(_Stop):
        await _async_main(["pipeline", "--web-allow", "python.org,*.github.com", "p.yaml", "g"])
    assert seen == [("python.org", "*.github.com")]


def test_search_keeps_allowed_and_drops_blocked() -> None:
    items = [("ok", "https://python.org/a", "s1"), ("bad", "https://evil.com/b", "s2")]
    out = _render_results(items, ("python.org",), 5)
    assert "https://python.org/a" in out
    assert "evil.com" not in out
    assert "1 result(s) hidden" in out


def test_search_empty_allowlist_hides_everything() -> None:
    items = [("bad", "https://evil.com/b", "s2")]
    out = _render_results(items, (), 5)
    assert out.startswith("No search results found.")
    assert "1 result(s) hidden" in out
