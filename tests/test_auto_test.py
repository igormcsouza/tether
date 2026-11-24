"""After the tests ran once, the harness re-runs them after each edit (#173, Aider's auto-test).

On paasio (qwen3.5:9b, 600 s cap) each whole-file rewrite took 30-100 s of model time and 2 of
them were typed blind and then refused, about 50 s lost; the model never saw whether a version
worked before typing the next one. Running the last test command after each edit shows it at once.
"""

from __future__ import annotations

from pathlib import Path

from tests.conftest import FakeScriptedProvider
from tether import ActionCall, Harness, ModelResponse
from tether.harness import is_test_cmd
from tether.sandbox import SandboxPolicy

TEST = "python3 -m unittest -q m_checks"
SUITE = "import unittest\nfrom m import f\n\n\nclass T(unittest.TestCase):\n"
SUITE += "    def test_f(self):\n        self.assertEqual(f(), 3)\n"


def _write(value: int, path: str = "m.py") -> str:
    return f"cat > {path} << 'EOF'\ndef f():\n    return {value}\nEOF"


async def _run(tmp_path: Path, cmds: list[str]) -> tuple[Harness, FakeScriptedProvider, str]:
    (tmp_path / "m_checks.py").write_text(SUITE)
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
    session = await h.run("goal")
    return h, provider, session.id


def _seen(provider: FakeScriptedProvider, call: int) -> str:
    return "\n".join(str(m.get("content") or "") for m in provider.recorded_calls[call])


async def test_each_edit_after_a_test_run_runs_the_tests(tmp_path: Path) -> None:
    # (values of another length: a same-size rewrite in the same second reuses the stale .pyc)
    _, provider, _ = await _run(tmp_path, [TEST, _write(100), _write(3), "ls"])
    first = _seen(provider, 2)
    assert f"[auto-test] `{TEST}`" in first and "AssertionError: 100 != 3" in first
    # the next version is written, not refused, and its run passes
    assert (tmp_path / "m.py").read_text().strip() == "def f():\n    return 3"
    assert "Tests pass after your last change" in _seen(provider, 3)


async def test_no_test_run_yet_means_no_auto_test(tmp_path: Path) -> None:
    _, provider, _ = await _run(tmp_path, [_write(1), _write(2), "ls"])
    assert "[auto-test]" not in _seen(provider, 2)


async def test_failing_auto_tests_count_toward_a_restart(tmp_path: Path) -> None:
    h, _, sid = await _run(tmp_path, [TEST, _write(4), _write(5), _write(6), "ls"])
    assert [t.event_type for t in h.store.get_turns(sid)].count("restart") == 1


PROBE = 'python3 -c "from unittest.mock import patch; print(1)"'


def test_is_test_cmd_true_for_runner_calls() -> None:
    for cmd in (
        "python3 -m unittest discover -p '*_test.py'",
        'pytest -q -k "foo"',
        "cd x && python -m pytest",
        "python3 -m unittest 2>&1 | head -50",
    ):
        assert is_test_cmd(cmd), cmd


def test_is_test_cmd_false_for_probes_quoted_or_heredoc_words() -> None:
    for cmd in (
        PROBE,
        "python3 -c 'import pytest'",
        "cat > t.py << 'EOF'\nimport unittest\nEOF",
        'python3 -c "from unittest.mock import patch\nprint(patch)"',  # a quote that spans lines
    ):
        assert not is_test_cmd(cmd), cmd


async def test_a_quoted_unittest_probe_does_not_replace_the_test_command(tmp_path: Path) -> None:
    # paasio: after the real tests, a `python3 -c` probe that imports unittest.mock was taken for
    # the test command, so the auto-test re-ran the probe instead of the suite
    _, provider, _ = await _run(tmp_path, [TEST, PROBE, _write(100), "ls"])
    after_edit = _seen(provider, 3)
    assert f"[auto-test] `{TEST}`" in after_edit and "AssertionError: 100 != 3" in after_edit
    assert f"[auto-test] `{PROBE}`" not in after_edit
