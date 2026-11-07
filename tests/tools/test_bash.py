"""Unit tests for tether/tools/bash.py (sandboxed shell tool)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tether import Harness, SandboxPolicy

FAILING_SUITE = "import unittest\n\n\nclass T(unittest.TestCase):\n" + "".join(
    f"    def test_{i}(self):\n        self.assertEqual({i}, -1)\n\n" for i in range(30)
)


def _mux(tmp_path: Path):
    sandbox = SandboxPolicy(workspace_root=tmp_path, use_kernel_sandbox=False)
    harness = Harness(db_path=tmp_path / "tether.db", tools=["bash"], sandbox=sandbox)
    return harness.build_multiplexer("ses_head", ["bash"], sandbox, "ollama/qwen3.5:9b")


@pytest.mark.parametrize(
    "cmd",
    [
        "bash python3 -m unittest discover -p '*_test.py' 2>&1 | head -40",
        "python3 -m unittest discover -p '*_test.py' 2>&1 | head -n 40",
        "python3 -m unittest -v x_test 2>&1 | head -40",
    ],
)
async def test_head_on_a_test_run_keeps_the_summary_and_exit_code(tmp_path: Path, cmd: str) -> None:
    """`<tests> | head -N` cut unittest's summary and hid the exit code (#173)."""
    (tmp_path / "x_test.py").write_text(FAILING_SUITE)
    out = (await _mux(tmp_path).execute(cmd)).output
    lines = out.splitlines()
    assert "Ran 30 tests" in out and "FAILED (failures=30)" in out and "[exit 1]" in out
    assert any("cut by `head`" in line for line in lines)
    assert len(lines) <= 40 + 8  # head's lines, the cut marker and the tail stay bounded
    assert lines[0] == (await _mux(tmp_path).execute(cmd.split(" | ")[0])).output.splitlines()[0]


async def test_head_on_short_test_output_or_other_commands_is_unchanged(tmp_path: Path) -> None:
    (tmp_path / "x_test.py").write_text(FAILING_SUITE.split("    def test_1(")[0])
    mux = _mux(tmp_path)
    short = (await mux.execute("python3 -m unittest x_test 2>&1 | head -100")).output
    assert "Ran 1 test" in short and "cut by" not in short
    (tmp_path / "f.txt").write_text("\n".join(map(str, range(50))))
    assert (await mux.execute("bash cat f.txt | head -3")).output.strip() == "0\n1\n2"


async def test_bash_tool(tmp_path: Path) -> None:
    """Verify bash --help, missing command error, inline command, and stdin script execution."""
    sandbox = SandboxPolicy(workspace_root=tmp_path, use_kernel_sandbox=False)
    harness = Harness(db_path=tmp_path / "tether.db", tools=["bash"], sandbox=sandbox)
    mux = harness.build_multiplexer("ses_bash", ["bash"], sandbox, "ollama/qwen3.5:9b")

    assert "Usage: bash" in (await mux.execute("bash --help")).output
    assert "Error: missing `<command>`" in (await mux.execute("bash")).output
    assert "hi_bash" in (await mux.execute("bash echo hi_bash")).output
    assert "hi_stdin" in (await mux.execute("bash", stdin="echo hi_stdin")).output
