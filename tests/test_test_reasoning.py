"""Before the first rewrite of a starting file, the model states what the tests expect (#173).

On pov and paasio (qwen3.5:9b) 6 of 6 runs failed with a different wrong first design each time,
and repair tools (runtime trace, fresh restart, blind-rewrite gate) never flipped one. AlphaCodium
(Ridnik et al., 2024, arXiv:2401.08500) has the model reason about the tests in plain words before
it writes code; that alone raised GPT-4's pass rate on CodeContests from 19% to 44%.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

from tests.conftest import FakeScriptedProvider
from tether import ActionCall, Harness, ModelResponse
from tether.harness import suite_for
from tether.sandbox import SandboxPolicy

SUITE = "import unittest\nfrom m import f\n\n\nclass T(unittest.TestCase):\n"
SUITE += "    def test_f(self):\n        self.assertEqual(f(), 3)\n"
WRITE = "cat > m.py << 'EOF'\ndef f():\n    return 3\nEOF"
REASONING = "test_f calls f() with no arguments and expects 3, so f returns the constant 3."


def _act(cmd: str) -> ModelResponse:
    return ModelResponse(content="", action=ActionCall(cmd=cmd))


async def _run(
    tmp_path: Path, script: list[ModelResponse], stub: bool = True
) -> FakeScriptedProvider:
    (tmp_path / "m_test.py").write_text(SUITE)
    if stub:
        (tmp_path / "m.py").write_text("def f():\n    pass\n")
        past = time.time() - 100
        os.utime(tmp_path / "m.py", (past, past))
    provider = FakeScriptedProvider(script)
    h = Harness(
        db_path=tmp_path / "t.db",
        tools=["bash"],
        provider=provider,
        max_steps=len(script),
        sandbox=SandboxPolicy(workspace_root=tmp_path, use_kernel_sandbox=False),
    )
    await h.run("goal")
    return provider


def _seen(provider: FakeScriptedProvider, call: int) -> str:
    return "\n".join(str(m.get("content") or "") for m in provider.recorded_calls[call])


async def test_the_first_rewrite_of_a_stub_asks_for_the_tests_in_plain_words(
    tmp_path: Path,
) -> None:
    script = [_act(WRITE), ModelResponse(content=REASONING, action=None), _act(WRITE), _act("ls")]
    h = await _run(tmp_path, script)
    asked = _seen(h, 1)
    assert "[BEFORE WRITING]" in asked and "m.py" in asked and "m_test.py" in asked
    # the plain-text reasoning is taken as the answer to that, not nudged as undelivered
    after = _seen(h, 2)
    assert REASONING in after and "not delivered" not in after
    assert "def f():\n    return 3" in (tmp_path / "m.py").read_text()  # the next write applies
    assert _seen(h, 3).count("[BEFORE WRITING]") == 1  # asked once per session


async def test_the_question_is_asked_once_even_if_ignored(tmp_path: Path) -> None:
    h = await _run(tmp_path, [_act(WRITE), _act(WRITE), _act("ls")])
    assert "return 3" in (tmp_path / "m.py").read_text()
    assert _seen(h, 2).count("[BEFORE WRITING]") == 1


async def test_a_new_file_or_no_tests_is_written_at_once(tmp_path: Path) -> None:
    h = await _run(tmp_path, [_act(WRITE), _act("ls")], stub=False)  # no starting file
    assert "[BEFORE WRITING]" not in _seen(h, 1) and "return 3" in (tmp_path / "m.py").read_text()
    other = tmp_path / "other"
    other.mkdir()
    (other / "m.py").write_text("def f():\n    pass\n")
    past = time.time() - 100
    os.utime(other / "m.py", (past, past))
    h = Harness(
        db_path=other / "t.db",
        tools=["bash"],
        provider=FakeScriptedProvider([_act(WRITE), _act("ls")]),
        max_steps=2,
        sandbox=SandboxPolicy(workspace_root=other, use_kernel_sandbox=False),
    )
    await h.run("goal")  # a starting file but no test file
    assert "return 3" in (other / "m.py").read_text()
    assert suite_for("m_test.py", tmp_path, time.time()) is None  # the tests themselves
    assert suite_for("gone.py", tmp_path, time.time()) is None
