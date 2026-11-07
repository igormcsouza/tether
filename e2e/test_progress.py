"""Live progress on stderr: `--verbose` step lines, and no noise by default. Scripted replies."""

from __future__ import annotations

import json

from e2e.conftest import Tether


def test_verbose_prints_one_stderr_line_per_step_and_keeps_stdout(tether: Tether, chaos) -> None:
    (tether.ws / "a.txt").write_text("hi\n")
    chaos.script(("edit view a.txt", ""), ("done", "the answer"))
    p = tether.cli("run", "--verbose", "--model", "e2e/scripted", "--tools", "edit", "go")
    assert p.stdout == "the answer\n"
    lines = [ln for ln in p.stderr.splitlines() if ln.startswith("[step ")]
    assert [ln.split("]")[1].split(" (")[0] for ln in lines] == [" edit view a.txt", " done"]
    assert "\r" not in p.stderr  # no dots when stderr is not a terminal


def test_a_piped_run_without_verbose_prints_only_the_session_id_on_stderr(
    tether: Tether, chaos
) -> None:
    chaos.script(("done", "ok"))
    p = tether.cli("run", "--model", "e2e/scripted", "go")
    assert p.stdout == "ok\n"
    sid = p.stderr.removeprefix("session ").strip()  # #90: there before the first model call
    assert p.stderr == f"session {sid}\n" and sid.startswith("ses_")
    assert tether.cli("status", sid).returncode == 0


def test_a_killed_json_run_still_names_its_session_on_stderr(tether: Tether, chaos) -> None:
    chaos.script(("done", "ok"))
    p = tether.cli("run", "--json", "--model", "e2e/scripted", "go")
    assert p.stderr.startswith("session ses_")
    assert p.stderr.split()[1] == json.loads(p.stdout)["id"]  # stdout JSON unchanged
