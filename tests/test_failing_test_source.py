"""A failing test run shows the failing test's own source, so the model sees the inputs (#173)."""

from __future__ import annotations

from pathlib import Path

from tests.conftest import FakeScriptedProvider
from tether import ActionCall, Harness, ModelResponse
from tether.harness import failing_test_source
from tether.sandbox import SandboxPolicy

BOOK_TEST = """import unittest

from book_store import total


class BookStoreTest(unittest.TestCase):
    def test_only_a_single_book(self):
        basket = [1]
        self.assertEqual(total(basket), 800)

    def test_four_groups_of_four(self):
        basket = [1, 1, 2, 2, 3, 3, 4, 5, 1, 1, 2, 2, 3, 3, 4, 5]
        self.assertEqual(total(basket), 10240)
"""


def _unittest_out(path: str, line: int, name: str) -> str:
    return (
        f"F.\n======\nFAIL: {name} (book_store_test.BookStoreTest.{name})\n"
        "Traceback (most recent call last):\n"
        f'  File "{path}", line {line}, in {name}\n'
        "    self.assertEqual(total(basket), 10240)\n"
        "AssertionError: 10400 != 10240\n\nRan 2 tests in 0.001s\n\nFAILED (failures=1)\n[exit 1]"
    )


def test_unittest_failure_shows_the_test_inputs(tmp_path: Path) -> None:
    (tmp_path / "book_store_test.py").write_text(BOOK_TEST)
    extra = failing_test_source(
        _unittest_out("book_store_test.py", 13, "test_four_groups_of_four"), tmp_path
    )
    assert "basket = [1, 1, 2, 2, 3, 3, 4, 5, 1, 1, 2, 2, 3, 3, 4, 5]" in extra
    assert "def test_four_groups_of_four" in extra
    assert "test_only_a_single_book" not in extra  # only the failing test, not the file


def test_absolute_frame_path_inside_the_workspace(tmp_path: Path) -> None:
    (tmp_path / "book_store_test.py").write_text(BOOK_TEST)
    out = _unittest_out(str(tmp_path / "book_store_test.py"), 13, "test_four_groups_of_four")
    assert "basket = [1, 1, 2, 2" in failing_test_source(out, tmp_path)


def test_frames_outside_the_workspace_are_never_read(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    (tmp_path / "secret_test.py").write_text(BOOK_TEST)
    assert (
        failing_test_source(_unittest_out("../secret_test.py", 13, "test_four_groups_of_four"), ws)
        == ""
    )
    out = _unittest_out(str(tmp_path / "secret_test.py"), 13, "test_four_groups_of_four")
    assert failing_test_source(out, ws) == ""


def test_missing_non_python_or_broken_files_add_nothing(tmp_path: Path) -> None:
    (tmp_path / "broken_test.py").write_text("def test_x(:\n")
    (tmp_path / "data_test.txt").write_text(BOOK_TEST)
    for path in ("nope_test.py", "broken_test.py", "data_test.txt"):
        assert failing_test_source(_unittest_out(path, 1, "test_x"), tmp_path) == ""
    assert failing_test_source("all good\nOK", tmp_path) == ""


def test_non_test_frames_are_skipped(tmp_path: Path) -> None:
    (tmp_path / "book_store.py").write_text("def total(b):\n    return b[0]\n")
    out = _unittest_out("book_store.py", 2, "total")
    assert failing_test_source(out, tmp_path) == ""


def test_source_already_in_the_output_is_not_repeated(tmp_path: Path) -> None:
    """pytest prints the failing test's source itself."""
    (tmp_path / "book_store_test.py").write_text(BOOK_TEST)
    out = _unittest_out("book_store_test.py", 13, "test_four_groups_of_four")
    out = "    def test_four_groups_of_four(self):\n" + out
    assert failing_test_source(out, tmp_path) == ""


def test_many_failures_stay_bounded(tmp_path: Path) -> None:
    body = "".join(
        f"    def test_{i}(self):\n        x = {list(range(60))}\n"
        "        self.assertEqual(x, 0)\n\n"
        for i in range(8)
    )
    (tmp_path / "big_test.py").write_text(
        "import unittest\n\n\nclass T(unittest.TestCase):\n" + body
    )
    out = "\n".join(_unittest_out("big_test.py", 7 + 4 * i, f"test_{i}") for i in range(8))
    extra = failing_test_source(out, tmp_path)
    assert extra.count("def test_") == 3  # at most 3 tests
    assert len(extra) <= 1500


async def test_failing_run_observation_carries_the_test_source(tmp_path: Path) -> None:
    (tmp_path / "book_store.py").write_text("def total(basket):\n    return 0\n")
    (tmp_path / "book_store_test.py").write_text(BOOK_TEST)
    cmds = ["python3 -m unittest book_store_test", "ls"]
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
    seen = "\n".join(m["content"] for m in provider.recorded_calls[1])
    assert "basket = [1, 1, 2, 2, 3, 3, 4, 5, 1, 1, 2, 2, 3, 3, 4, 5]" in seen
    assert "basket = [1]" in seen  # both tests fail: both sources shown
