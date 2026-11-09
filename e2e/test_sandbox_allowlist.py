"""e2e: `--allow` runs a listed prefix outside the jail (#59, #124 item 4). Scripted, no model:
the proxy forces the commands, so tether alone decides what runs outside and what is refused."""

from __future__ import annotations

import json

from e2e.conftest import Tether


def test_allowed_prefix_runs_outside_with_scrubbed_env(tether: Tether, chaos) -> None:
    chaos.script("bash env", "bash env; id", "bash cat .tether/allow.json", ("done", "ok"))
    r = tether.run("outside", "--tools", "bash", "--allow", "env", "--allow-unsandboxed")
    outs = tether.tool_outputs(r["id"])[:3]
    assert f"HOME={tether.home}" in outs[0], outs[0]  # real HOME: it ran outside bwrap
    assert "sekret-value-123" not in outs[0] and "E2E_KEY" not in outs[0], outs[0]
    assert "runs outside the jail" in outs[1] and "Instead:" in outs[1], outs[1]
    assert "Sandbox violation" in outs[2] or "No such file" in outs[2], outs[2]


def test_allow_file_is_merged_and_bad_file_is_loud(tether: Tether, chaos) -> None:
    (tether.ws / ".tether").mkdir()
    allow = tether.ws / ".tether" / "allow.json"
    allow.write_text(json.dumps({"allow": ["env"]}))
    chaos.script(
        "bash env", ("edit write .tether/allow.json", '{"allow":["bash"]}'), ("done", "ok")
    )
    r = tether.run("file", "--tools", "bash,edit", "--allow-unsandboxed")
    outs = tether.tool_outputs(r["id"])[:2]
    assert f"HOME={tether.home}" in outs[0], outs[0]
    assert "protected" in outs[1], outs[1]
    assert json.loads(allow.read_text()) == {"allow": ["env"]}
    allow.write_text("{not json")
    p = tether.cli("run", "--model", "e2e/scripted", "--allow-unsandboxed", "goal")
    assert p.returncode == 1 and "allow.json" in p.stderr and "Traceback" not in p.stderr, p.stderr


def test_bad_allow_flag_is_a_usage_error(tether: Tether) -> None:
    p = tether.cli("run", "--allow", "git;rm", "goal")
    assert p.returncode == 1 and "--allow" in p.stderr, (p.returncode, p.stderr)
