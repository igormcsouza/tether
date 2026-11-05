"""After a test run, name the tests the last change broke: passed last run, fail now (#173)."""

from __future__ import annotations

from pathlib import Path

from tests.conftest import FakeScriptedProvider
from tether import ActionCall, Harness, ModelResponse
from tether.harness import regression_note, run_outcome
from tether.sandbox import SandboxPolicy

UNITTEST_OUT = """.F
======================================================================
FAIL: test_b (mod_test.T.test_b)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "mod_test.py", line 6, in test_b
AssertionError: 0 != 2

======================================================================
ERROR: test_c (mod_test.T.test_c)
----------------------------------------------------------------------
Traceback (most recent call last):
TypeError: boom

----------------------------------------------------------------------
Ran 3 tests in 0.001s

FAILED (failures=1, errors=1)
"""

PYTEST_OUT = """mod_test.py .FE
FAILED mod_test.py::test_b - assert 0 == 2
ERROR mod_test.py::T::test_c - TypeError: boom
========= 1 failed, 1 passed, 1 error in 0.03s =========
"""


def test_outcome_reads_unittest_and_pytest() -> None:
    assert run_outcome(UNITTEST_OUT) == (3, frozenset({"test_b", "test_c"}))
    assert run_outcome(PYTEST_OUT) == (3, frozenset({"test_b", "test_c"}))
    assert run_outcome("..\n----\nRan 2 tests in 0.0s\n\nOK\n") == (2, frozenset())
    assert run_outcome("===== 4 passed in 0.01s =====") == (4, frozenset())


def test_outcome_is_none_without_a_test_summary() -> None:
    assert run_outcome("Traceback (most recent call last):\nImportError: no mod") is None
    assert run_outcome("[exit 0: no output] Command succeeded.") is None


def test_note_names_broken_and_fixed_tests() -> None:
    note = regression_note((3, frozenset({"test_b"})), (3, frozenset({"test_a", "test_c"})))
    assert note.startswith("\n[regression]")
    assert "test_a" in note and "test_c" in note  # broke
    assert "test_b" in note  # newly passing
    assert note.index("test_a") < note.index("test_b")


def test_no_note_when_nothing_broke_or_runs_differ() -> None:
    assert regression_note((3, frozenset({"test_a", "test_b"})), (3, frozenset({"test_b"}))) == ""
    assert regression_note((3, frozenset({"test_a"})), (3, frozenset({"test_a"}))) == ""
    # a different number of tests ran (e.g. one test selected): not comparable
    assert regression_note((3, frozenset()), (1, frozenset({"test_a"}))) == ""


def test_note_stays_bounded() -> None:
    many = frozenset(f"test_case_number_{i:03d}_with_a_long_descriptive_name" for i in range(40))
    note = regression_note((40, frozenset()), (40, many))
    assert len(note) <= 400
    assert "more" in note


TEST_FILE = """import unittest
from mod import f, g


class T(unittest.TestCase):
    def test_a(self):
        self.assertEqual(f(), 1)

    def test_b(self):
        self.assertEqual(g(), 2)
"""


async def test_the_observation_after_a_regressing_change_names_it(tmp_path: Path) -> None:
    (tmp_path / "mod_test.py").write_text(TEST_FILE)
    (tmp_path / "v1.py").write_text("def f():\n    return 1\n\n\ndef g():\n    return 0\n")
    # a different size, so Python does not reuse v1's cached bytecode written in the same second
    (tmp_path / "v2.py").write_text("def f():\n    return 0\n\n\ndef g():\n    return 2  # v2\n")
    test = "python3 -m unittest mod_test"
    cmds = ["cp v1.py mod.py", test, "cp v2.py mod.py", test, "ls"]
    provider = FakeScriptedProvider(
        [ModelResponse(content="", action=ActionCall(cmd=c)) for c in cmds]
    )
    h = Harness(
        db_path=tmp_path / "t.db",
        tools=["bash"],
        provider=provider,
        max_steps=len(cmds),
        sandbox=SandboxPolicy(workspace_root=tmp_path, use_kernel_sandbox=False),
    )
    await h.run("goal")

    def seen(call: int) -> str:
        return "\n".join(str(m.get("content") or "") for m in provider.recorded_calls[call])

    assert "[regression]" not in seen(2)  # first test run: nothing to compare with
    after = seen(4).split("[regression]", 1)
    assert len(after) == 2
    assert "test_a" in after[1].splitlines()[0] and "test_b" in after[1].splitlines()[0]
