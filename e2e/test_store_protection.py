"""A session store inside the workspace is refused to `bash` and `edit` (AD-55).

Scripted: replies are fixed, so the result never depends on the model.
"""

from __future__ import annotations

from e2e.conftest import Tether


def test_store_in_workspace_is_refused(tether: Tether, chaos) -> None:
    chaos.script(
        ("python3 -c \"import sqlite3; print(sqlite3.connect('s.db').execute('select 1'))\"", None),
        ("edit view s.db-wal", None),
        ("done", "ok"),
    )
    store = {"TETHER_DB": str(tether.ws / "s.db")}
    p = tether.cli("run", "--json", "--model", f"e2e/{tether.model}", "--tools", "bash,edit",
                   "--max-steps", "4", "read it", env=store)  # fmt: skip
    assert p.returncode == 0, p.stderr
    import sqlite3

    c = sqlite3.connect(tether.ws / "s.db")
    outs = [r[0] for r in c.execute("select content from turns where role='tool' order by id")]
    assert "session store `s.db`" in outs[0] and "session store" in outs[1], outs
