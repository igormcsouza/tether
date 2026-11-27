"""A big JSON reply is read by path; `web:fetch` runs as `web fetch`; `curl` without bash points
to `web fetch` (gap hunt: a 6 MB PyPI reply cost qwen3.5:9b ~20 steps).

Scripted: replies are fixed, so the result never depends on the model. The JSON is served from
a local thread, so the scenario runs offline.
"""

from __future__ import annotations

import http.server
import json
import threading
from pathlib import Path

from e2e.conftest import Tether


def test_big_json_by_path_and_tool_colon_verb(tether: Tether, chaos, tmp_path: Path) -> None:
    data = {"info": {"version": "0.17.6", "readme": "x" * 20000}, "releases": {"0.1": []}}
    (tmp_path / "p.json").write_text(json.dumps(data))

    class H(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):  # type: ignore[no-untyped-def]
            super().__init__(*a, directory=str(tmp_path), **k)

        def log_message(self, *a):  # type: ignore[no-untyped-def]
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_port}/p.json"
    tether.env["TETHER_WEB_ALLOW_PRIVATE"] = "1"
    try:
        chaos.script(
            (f"web:fetch {url}", None),
            (f"web fetch {url}#info/version", None),
            (f"curl -s {url}", None),
            ("done", "0.17.6"),
        )
        r = tether.run("read the version", "--tools", "web", "--max-steps", "6")
    finally:
        srv.shutdown()
    assert r["rc"] == 0, r
    outputs = tether.tool_outputs(r["id"])
    assert outputs[0].startswith("[JSON at #/: {2 keys}") and f"{url}#/info" in outputs[0]
    assert outputs[1] == '[#/info/version]\n"0.17.6"'
    assert "has no shell" in outputs[2] and "web fetch <url>#/key/path" in outputs[2]
