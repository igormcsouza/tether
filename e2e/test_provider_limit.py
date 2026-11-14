# Provider usage limit (#305), end to end: a command provider reports its usage limit.
# Scripted: no model is used; the command is a local script.

from __future__ import annotations

import sys
from pathlib import Path

import yaml

from e2e.conftest import Tether

LIMIT = """import json, os, sys
counter = sys.argv[1]
n = int(open(counter).read()) if os.path.exists(counter) else 0
open(counter, "w").write(str(n + 1))
sys.stdin.read()
print(json.dumps({"is_error": True, "result": "Claude usage limit reached. Resets 1:30pm"}))
sys.exit(1)
"""


def test_usage_limit_fails_at_once_with_provider_words(tether: Tether, tmp_path: Path) -> None:
    counter = tmp_path / "counter"
    script = tmp_path / "limit.py"
    script.write_text(LIMIT)
    providers = tmp_path / "providers.yaml"
    entry = {
        "kind": "command",
        "argv": [sys.executable, str(script), str(counter)],
        "stdin": "{conversation}",
        "reply": "result",
    }
    providers.write_text(yaml.safe_dump({"e2elimit": entry}))
    r = tether.run("answer", prefix="e2elimit")
    assert r["status"] == "FAILED", r
    assert "usage limit reached" in r["failure"]["message"], r
    assert "--model" in r["failure"]["message"], r
    assert counter.read_text() == "1", "a usage limit is not retried"
