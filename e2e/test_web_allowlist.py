"""e2e: `--web-allow` reaches the real `web` tool (#124 item 5). Scripted, no model, no egress:
the forced targets are an IP literal and an off-list host, both refused before any connect."""

from __future__ import annotations

from e2e.conftest import Tether


def test_web_allow_refuses_off_list_hosts(tether: Tether, chaos) -> None:
    chaos.script(
        "web fetch http://127.0.0.1:9/",
        "web fetch https://evil.invalid/",
        ("done", "ok"),
    )
    r = tether.run("fetch off-list", "--tools", "web", "--web-allow", "python.org")
    outs = tether.tool_outputs(r["id"])[:2]
    assert all("host not allowed" in o and "Instead:" in o and "python.org" in o for o in outs), (
        outs
    )


def test_bad_web_allow_is_a_usage_error(tether: Tether) -> None:
    p = tether.cli("run", "--web-allow", "https://python.org", "goal")
    assert p.returncode == 1, (p.returncode, p.stderr)
    assert "--web-allow" in p.stderr and "bare domain" in p.stderr, p.stderr
