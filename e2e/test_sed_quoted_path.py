"""sed -n 'a,bp file' with the path typed inside the quotes runs as sed -n 'a,bp' file (#270)."""

from __future__ import annotations

from e2e.conftest import Tether


def test_sed_with_path_inside_quotes_runs(tether: Tether, chaos) -> None:
    (tether.ws / "f.txt").write_text("one\ntwo\nthree\n")
    chaos.script("sed -n '1,2p f.txt'", ("done", "ok"))
    r = tether.run("show the first lines of f.txt", "--tools", "bash")
    out = tether.tool_outputs(r["id"])[0]
    assert "one" in out and "two" in out
    assert "extra characters" not in out
