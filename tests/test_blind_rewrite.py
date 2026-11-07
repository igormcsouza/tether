"""A whole-file rewrite with no test run since the last one is refused until the tests run (#173).

On current main a paasio run hit the 600 s cap after 13 whole-file rewrites of paasio.py, 5 of them
in a row with no test run between (about 40 s of model time each): the model never saw whether a
version worked before typing the next one.
"""

from __future__ import annotations

from pathlib import Path

from tests.conftest import FakeScriptedProvider
from tether import ActionCall, Harness, ModelResponse
from tether.sandbox import SandboxPolicy

TEST = "python3 -m unittest -q m_test"
SUITE = "import unittest\nfrom m import f\n\n\nclass T(unittest.TestCase):\n"
SUITE += "    def test_f(self):\n        self.assertEqual(f(), 3)\n"


def _write(value: int, path: str = "m.py") -> str:
    return f"cat > {path} << 'EOF'\ndef f():\n    return {value}\nEOF"


async def _run(tmp_path: Path, cmds: list[str]) -> tuple[Harness, FakeScriptedProvider]:
    (tmp_path / "m_test.py").write_text(SUITE)
    (tmp_path / "m.py").write_text("def f():\n    return 0\n")
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
    return h, provider


def _seen(provider: FakeScriptedProvider, call: int) -> str:
    return "\n".join(str(m.get("content") or "") for m in provider.recorded_calls[call])


async def test_a_blind_second_rewrite_is_refused(tmp_path: Path) -> None:
    _, provider = await _run(tmp_path, [TEST, _write(1), _write(2), TEST, _write(3), "ls"])
    blocked = _seen(provider, 3)
    assert "[BLOCKED]" in blocked and "m.py" in blocked and TEST in blocked
    # writes after a test run apply, and are not refused
    assert (tmp_path / "m.py").read_text().strip() == "def f():\n    return 3"
    assert _seen(provider, 5).count("[BLOCKED]") == 1


async def test_the_refused_write_leaves_the_file_as_it_was(tmp_path: Path) -> None:
    await _run(tmp_path, [TEST, _write(1), _write(2)])
    assert (tmp_path / "m.py").read_text().strip() == "def f():\n    return 1"


async def test_every_blind_rewrite_is_refused_until_the_tests_run(tmp_path: Path) -> None:
    """On paasio 4 untested 1-line rewrites followed one refusal; a test run is all it takes."""
    cmds = [TEST, _write(1), _write(2), _write(3), TEST, _write(4)]  # (an identical repeat loops)
    _, provider = await _run(tmp_path, cmds)
    assert _seen(provider, 4).count("[BLOCKED]") == 2  # both blind rewrites refused, not just one
    assert (tmp_path / "m.py").read_text().strip() == "def f():\n    return 4"


async def test_no_test_run_yet_or_another_file_is_not_refused(tmp_path: Path) -> None:
    _, provider = await _run(tmp_path, [_write(1), _write(2), TEST, _write(4, "n.py"), _write(5)])
    assert all("[BLOCKED]" not in _seen(provider, i) for i in range(5))
    assert (tmp_path / "m.py").read_text().strip() == "def f():\n    return 5"
