"""When the same tests fail again after a change, the run shows what the code did (#173).

On pov (qwen3.5:9b, main) the same 2 tests failed at steps 6, 9 and 15 with only the final trees in
the assertion; 5 whole-file rewrites in between did not touch the bug. DebugRepair (Wu et al., 2026,
arXiv:2604.19305) fixes 51% more bugs across 5 models by showing intermediate runtime values instead
of outcome-level failures only; its rule-based instrumentation needs no model call.
"""

from __future__ import annotations

from pathlib import Path

from tests.conftest import FakeScriptedProvider
from tether import ActionCall, Harness, ModelResponse
from tether.sandbox import SandboxPolicy
from tether.trace import TRACE_LIMIT, failing_test_id, runtime_trace

SOLUTION = (
    "class Node:\n"
    "    def __init__(self, label, kids=None):\n"
    "        self.label = label\n"
    "        self.kids = kids or []\n\n\n"
    "def depth(node):\n"
    "    return 1 + max((depth(k) for k in node.kids[:1]), default=0)\n"
)
SUITE = (
    "import unittest\nfrom tree import Node, depth\n\n\n"
    "class TreeTest(unittest.TestCase):\n"
    "    def test_depth(self):\n"
    "        self.assertEqual(depth(Node('a', [Node('b'), Node('c', [Node('d')])])), 3)\n"
)
TEST = "python3 -m unittest -q tree_test"


def _sandbox(tmp_path: Path) -> SandboxPolicy:
    return SandboxPolicy(workspace_root=tmp_path, use_kernel_sandbox=False)


def test_failing_test_id_from_unittest_and_pytest() -> None:
    assert failing_test_id("FAIL: test_x (pov_test.PovTest.test_x)\n") == "pov_test.PovTest.test_x"
    assert failing_test_id("ERROR: test_x (pov_test.PovTest)\n") == "pov_test.PovTest.test_x"
    assert failing_test_id("FAILED sub/a_test.py::T::test_y - x\n") == "sub.a_test.T.test_y"
    assert failing_test_id("FAILED a_test.py::test_z - boom\n") == "a_test.test_z"
    assert failing_test_id("Ran 3 tests\nOK\n") is None


async def test_runtime_trace_shows_calls_args_and_returns(tmp_path: Path) -> None:
    (tmp_path / "tree.py").write_text(SOLUTION)
    (tmp_path / "tree_test.py").write_text(SUITE)
    trace = await runtime_trace(_sandbox(tmp_path), "tree_test.TreeTest.test_depth")
    assert trace.startswith("\n[runtime trace of test_depth")
    assert "depth(node=Node(label='a'" in trace  # objects show their fields, not an address
    assert "-> 2" in trace and "object at 0x" not in trace
    assert "tree_test" not in trace.split("\n", 2)[2]  # only calls into the code under test
    assert len(trace) <= TRACE_LIMIT


async def test_runtime_trace_is_empty_when_nothing_ran(tmp_path: Path) -> None:
    assert await runtime_trace(_sandbox(tmp_path), "missing_test.T.test_q") == ""


async def test_the_trace_is_added_when_the_same_tests_fail_after_a_change(tmp_path: Path) -> None:
    (tmp_path / "tree.py").write_text(SOLUTION)
    (tmp_path / "tree_test.py").write_text(SUITE)
    change = "echo '# tried' >> tree.py"
    cmds = [TEST, change, TEST, TEST, "ls"]
    provider = FakeScriptedProvider(
        [ModelResponse(content="", action=ActionCall(cmd=c)) for c in cmds]
    )
    h = Harness(
        db_path=tmp_path / "t.db",
        tools=["bash"],
        provider=provider,
        max_steps=len(cmds),
        sandbox=_sandbox(tmp_path),
    )
    await h.run("goal")

    def seen(call: int) -> str:
        return "\n".join(str(m.get("content") or "") for m in provider.recorded_calls[call])

    assert "[runtime trace" not in seen(1)  # a first failure: the usual output is enough
    assert seen(3).count("[runtime trace of test_depth") == 1  # same failure after a change
    assert seen(4).count("[runtime trace of test_depth") == 1  # once per failing set
