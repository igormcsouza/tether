"""Interfaces around the loop: other providers, MCP, telemetry, web and skills' own tools."""

from __future__ import annotations

import asyncio
import json
import sys

from e2e.conftest import Tether


# --- providers: the same loop over every wire format ---------------------------------------
def test_openai_wire_format(tether: Tether, chaos) -> None:
    chaos.script(("done", "via openai"))
    r = tether.run("go", prefix="e2eopenai")
    assert (r["rc"], r["result"]) == (0, "via openai"), r
    assert chaos.headers[0]["authorization"] == "Bearer sekret-value-123"
    req = chaos.requests[0]
    assert [t["function"]["name"] for t in req["tools"]] == ["act"] and req["messages"][0][
        "role"
    ] == "system"


def test_anthropic_wire_format(tether: Tether, chaos) -> None:
    chaos.script(("done", "via anthropic"))
    r = tether.run("go", prefix="e2eanthropic")
    assert (r["rc"], r["result"]) == (0, "via anthropic"), r
    assert chaos.headers[0]["x-api-key"] == "sekret-value-123"
    req = chaos.requests[0]
    assert [t["name"] for t in req["tools"]] == ["act"] and "system" in req


def test_declared_command_provider(tether: Tether, chaos) -> None:
    r = tether.run("go", prefix="e2ecmd")
    assert (r["rc"], r["result"]) == (0, "from command"), r


# --- web tool through the env overrides -------------------------------------------------------
def test_web_search_uses_searxng_override(tether: Tether, chaos) -> None:
    chaos.pages["/search"] = (
        "application/json",
        json.dumps(
            {
                "results": [
                    {
                        "title": "Teal facts",
                        "url": "https://example.test/teal",
                        "content": "teal is a colour",
                    }
                ]
            }
        ),
    )
    chaos.script("web search teal", ("done", "ok"))
    tether.env["SEARXNG_URL"] = chaos.url
    r = tether.run("search", "--tools", "web")
    out = tether.tool_outputs(r["id"])[0]
    assert "Teal facts" in out and "https://example.test/teal" in out and len(out) < 1200


def test_web_fetch_reads_a_page_when_private_hosts_are_allowed(tether: Tether, chaos) -> None:
    chaos.pages["/page"] = (
        "text/html",
        "<html><body><h1>Hello pineapple</h1><p>body text</p></body></html>",
    )
    tether.env["TETHER_WEB_ALLOW_PRIVATE"] = "1"
    chaos.script(f"web fetch {chaos.url}/page", ("done", "ok"))
    r = tether.run("fetch", "--tools", "web")
    assert "Hello pineapple" in tether.tool_outputs(r["id"])[0]


# --- skills' own tools.py ----------------------------------------------------------------------
def _skill(t: Tether, listed: bool) -> None:
    d = t.ws / "skills" / "greeter"
    d.mkdir(parents=True)
    tools = "[greet]" if listed else "[bash]"
    (d / "SKILL.md").write_text(
        f"---\nname: greeter\ndescription: greets\ntools: {tools}\n---\nGreet people.\n"
    )
    (d / "tools.py").write_text(
        "from tether import tool\n\n\n@tool(name='greet', description='Say hello')\n"
        "def greet(name: str) -> str:\n    return f'hello {name}'\n"
    )


def test_skill_tools_py_runs_when_listed(tether: Tether, chaos) -> None:
    _skill(tether, listed=True)
    chaos.script("greet world", ("done", "ok"))
    r = tether.run("go", "--skill", "greeter")
    assert tether.tool_outputs(r["id"])[0] == "hello world"
    assert "- greet:" in chaos.requests[0]["messages"][0]["content"]


def test_skill_tool_not_listed_stays_unknown_and_warns(tether: Tether, chaos) -> None:
    _skill(tether, listed=False)
    chaos.script("greet world", ("done", "ok"))
    r = tether.run("go", "--skill", "greeter")
    assert "unknown command `greet`" in tether.tool_outputs(r["id"])[0]
    assert "greet" in r["stderr"] and "tools" in r["stderr"], "an unlisted @tool must warn"


# --- telemetry: stats, events, misses, retro -----------------------------------------------
def test_stats_events_and_misses_see_the_friction(tether: Tether, chaos) -> None:
    chaos.script("bash true", "bash true", ("done", "ok"))  # second one is a loop_stall
    r = tether.run("friction", "--tools", "bash")
    stats = json.loads(tether.cli("stats", "--json").stdout)
    assert "loop_stall" in json.dumps(stats) and r["id"]
    events = tether.cli("events", r["id"]).stdout
    assert "loop_stall" in events or "loop" in events.lower(), events
    assert tether.cli("misses").returncode == 0


def test_retro_proposes_rules_but_never_touches_the_skill_without_apply(
    tether: Tether, chaos
) -> None:
    _skill(tether, listed=True)
    skill_md = tether.ws / "skills" / "greeter" / "SKILL.md"
    before = skill_md.read_text()
    chaos.script(
        "greet world", "greet world", ("done", "ok")
    )  # loop_stall = friction to learn from
    r = tether.run("go", "--skill", "greeter")
    chaos.script(
        {"text": "- Never repeat the same command twice in a row.\n- Call done when finished."}
    )
    p = tether.cli("retro", r["id"], "--model", "e2e/scripted")
    assert p.returncode == 0, p.stderr
    assert skill_md.read_text() == before, "retro without --apply must not edit the skill"


# --- MCP server over stdio ---------------------------------------------------------------------
def test_mcp_server_runs_a_session_over_stdio(tether: Tether, chaos) -> None:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    chaos.script(("done", "via mcp"))

    async def go() -> dict:
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "tether.cli", "mcp", "--workspace", str(tether.ws)],
            env=tether.env,
            cwd=str(tether.ws),
        )
        async with stdio_client(params) as (rd, wr), ClientSession(rd, wr) as s:
            await s.initialize()
            names = {t.name for t in (await s.list_tools()).tools}
            res = await s.call_tool("tether_run", {"goal": "go", "model": "e2e/scripted"})
            return {"names": names, "run": json.loads(res.content[0].text)}

    out = asyncio.run(asyncio.wait_for(go(), 60))
    assert out["names"] >= {
        "tether_run",
        "tether_status",
        "tether_wait",
        "tether_read",
        "tether_send",
    }
    assert out["run"]["status"] == "COMPLETED" and out["run"]["result"] == "via mcp"
