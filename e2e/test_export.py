"""`tether export`: a finished session renders as Markdown, --out writes a file, unknown ids fail.
Scripted: the proxy plays the model, tether is real."""

from __future__ import annotations

from e2e.conftest import Tether


def test_export_renders_goal_and_step_as_markdown(tether: Tether, chaos) -> None:
    chaos.script("bash echo hello-export", ("done", "exported"))
    r = tether.run("export me", "--tools", "bash")
    p = tether.cli("export", r["id"])
    assert p.returncode == 0, p.stderr
    assert p.stdout.splitlines()[0] == f"# Session {r['id']}"
    assert "export me" in p.stdout
    assert "## Step 1" in p.stdout
    assert "echo hello-export" in p.stdout
    assert "hello-export" in tether.tool_outputs(r["id"])[0]


def test_export_out_writes_the_file_instead_of_stdout(tether: Tether, chaos) -> None:
    chaos.script("bash echo x", ("done", "ok"))
    r = tether.run("write me", "--tools", "bash")
    p = tether.cli("export", r["id"], "--out", "session.md")
    assert p.returncode == 0, p.stderr
    assert "# Session" not in p.stdout
    text = (tether.ws / "session.md").read_text()
    assert text.startswith(f"# Session {r['id']}")
    assert "## Step 1" in text


def test_export_unknown_id_exits_1_with_not_found(tether: Tether, chaos) -> None:
    chaos.script(("done", "ok"))
    tether.run("seed the db")
    p = tether.cli("export", "ses_doesnotexist")
    assert p.returncode == 1
    assert "not found" in p.stderr
