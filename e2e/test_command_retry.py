# Command provider retry (#268), end to end: a command that hangs once, then answers.
# Scripted: no model is used; the command is a local script.

from __future__ import annotations

import sys
from pathlib import Path

import yaml

from e2e.conftest import Tether

FLAKY = """import json, os, sys, time
counter = sys.argv[1]
n = int(open(counter).read()) if os.path.exists(counter) else 0
open(counter, "w").write(str(n + 1))
sys.stdin.read()
if n == 0:
    time.sleep(30)
print(json.dumps({"result": 'act("done", stdin="from flaky")'}))
"""


def test_hung_command_is_retried_and_session_completes(tether: Tether, tmp_path: Path) -> None:
    counter = tmp_path / "counter"
    script = tmp_path / "flaky.py"
    script.write_text(FLAKY)
    providers = tmp_path / "providers.yaml"
    entry = {
        "kind": "command",
        "argv": [sys.executable, str(script), str(counter)],
        "stdin": "{conversation}",
        "reply": "result",
        "timeout": 2,
    }
    providers.write_text(yaml.safe_dump({"e2eflaky": entry}))
    r = tether.run("answer", prefix="e2eflaky")
    assert (r["rc"], r["status"], r["result"]) == (0, "COMPLETED", "from flaky"), r
    assert counter.read_text() == "2", "the hung attempt is retried once"
