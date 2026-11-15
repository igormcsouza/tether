"""F2: a fetch with #anchor and --from that cannot run is reported, not crashed.

Scripted: replies are fixed, so the result never depends on the model.
"""

from __future__ import annotations

from e2e.conftest import Tether


def test_bad_fetch_with_anchor_and_from_reports_error(tether: Tether, chaos) -> None:
    # ftp is refused before any network I/O, so the scenario is deterministic offline
    fetch = "web fetch ftp://example.org/page#top --from intro"
    chaos.script((fetch, None), ("done", "stopped"))
    r = tether.run("fetch", "--tools", "web", "--max-steps", "5")
    assert r["rc"] == 0, r
    outputs = tether.tool_outputs(r["id"])
    assert any("URL must start with http:// or https://" in o for o in outputs), outputs
