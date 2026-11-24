"""A quoted `unittest` probe is not the test command: [auto-test] re-runs the real suite (scripted).

paasio (qwen3.5:9b): a `python3 -c` probe that imported `unittest.mock` became the test command, so
the auto-test after each edit ran the probe and the model never saw the suite's result.
"""

from __future__ import annotations

from e2e.conftest import Tether

TEST = (
    "import unittest\nimport a\n\n\nclass T(unittest.TestCase):\n"
    "    def test_x(self):\n        self.assertEqual(a.X, 2)\n"
)
RUN = "python3 -m unittest test_t 2>&1"
PROBE = 'python3 -c "from unittest.mock import patch; print(1)"'


def test_auto_test_after_a_probe_runs_the_real_suite(tether: Tether, chaos) -> None:
    (tether.ws / "test_t.py").write_text(TEST)
    chaos.script(RUN, PROBE, ("edit write a.py", "X = 2\n"), ("done", "ok"))
    d = tether.run("make the test pass", "--tools", "edit,bash", "--max-steps", "10")
    outputs = "\n".join(tether.tool_outputs(d["id"]))
    assert f"[auto-test] `{RUN}`" in outputs, "the edit re-ran the real suite"
    assert f"[auto-test] `{PROBE}`" not in outputs, "the probe is not the test command"
