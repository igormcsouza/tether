"""e2e: escalation asks the caller once, then remembers (#59, #124 item 4). Scripted, no
model: the proxy forces the commands; tether alone decides what pauses, runs or is refused."""

from __future__ import annotations

import json

from e2e.conftest import Tether


def test_push_pauses_then_approve_runs_outside_and_remembers(tether: Tether, chaos) -> None:
    chaos.script(
        "bash git push origin main", ("done", "ok"), "bash git push origin x", ("done", "ok")
    )
    r = tether.run("push", "--tools", "bash")
    assert r["rc"] == 2 and r["status"] == "WAITING_INPUT", r
    assert r["result"].startswith("[APPROVAL NEEDED] git push origin main"), r["result"]
    assert r["approval"] == {"command": "git push origin main", "prefix": "git push"}, r
    allow = tether.ws / ".tether" / "allow.json"
    assert not allow.exists()
    s = tether.send(r["id"], "approve")
    assert s["rc"] == 0 and s["status"] == "COMPLETED" and "approval" not in s, s
    assert json.loads(allow.read_text()) == {"allow": ["git push"]}
    follow = [t["content"] for t in tether.turns(r["id"]) if t["role"] == "user"]
    assert any("ran outside the jail" in f and "git" in f for f in follow), follow
    # A new session in the same workspace runs the approved prefix with no pause.
    r2 = tether.run("push again", "--tools", "bash")
    assert r2["rc"] == 0 and r2["status"] == "COMPLETED" and "approval" not in r2, r2
    assert "APPROVAL NEEDED" not in tether.tool_outputs(r2["id"])[0]


def test_deny_runs_nothing_and_foreground_request_is_on_stderr(tether: Tether, chaos) -> None:
    chaos.script("bash gh pr list", ("done", "ok"))
    p = tether.cli("run", "--model", "e2e/scripted", "--tools", "bash", "list prs")
    assert p.returncode == 2 and p.stdout.strip() == "", (p.returncode, p.stdout)
    assert "[APPROVAL NEEDED] gh pr list" in p.stderr and "tether send" in p.stderr, p.stderr
    sid = p.stderr.split("session ", 1)[1].split()[0]
    s = tether.send(sid, "no, use the web UI")
    assert s["status"] == "COMPLETED", s
    assert not (tether.ws / ".tether" / "allow.json").exists()
    follow = [t["content"] for t in tether.turns(sid) if t["role"] == "user"]
    assert any("did not allow" in f and "use the web UI" in f for f in follow), follow


def test_read_only_git_and_metacharacters_never_pause(tether: Tether, chaos) -> None:
    chaos.script("bash git status", "bash git push; id", ("done", "ok"))
    r = tether.run("mixed", "--tools", "bash")
    assert r["rc"] == 0 and r["status"] == "COMPLETED" and "approval" not in r, r
    outs = tether.tool_outputs(r["id"])[:2]
    assert "APPROVAL NEEDED" not in outs[0], outs[0]
    assert "metacharacters" in outs[1] and "APPROVAL NEEDED" not in outs[1], outs[1]
