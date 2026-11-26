"""A name an import cannot find is located in the workspace module (AD-52)."""

from __future__ import annotations

from pathlib import Path

from tests.conftest import FakeScriptedProvider
from tether import ActionCall, Harness, ModelResponse
from tether.harness import import_hint
from tether.sandbox import SandboxPolicy

GO = """import os
from typing import Any as Alias


class Board:
    WHITE = 'W'
    size: int = 0

    def territory(self):
        limit = 3
        return limit


def helper():
    pass
"""


def _err(name: str, module: str = "go") -> str:
    return f"ImportError: cannot import name '{name}' from '{module}' ({module}.py)"


def test_a_name_inside_a_class_or_function_is_located(tmp_path: Path) -> None:
    (tmp_path / "go.py").write_text(GO)
    hint = import_hint(_err("WHITE"), tmp_path)
    assert "`WHITE` is defined inside `class Board` in go.py" in hint
    assert "`limit` is defined inside `def territory`" in import_hint(
        "AttributeError: module 'go' has no attribute 'limit'", tmp_path
    )


def test_a_name_defined_nowhere_says_so(tmp_path: Path) -> None:
    (tmp_path / "go.py").write_text(GO)
    assert "go.py defines no top-level `BLACK`" in import_hint(_err("BLACK"), tmp_path)


def test_top_level_names_add_nothing(tmp_path: Path) -> None:
    (tmp_path / "go.py").write_text(GO + "x = y = 1\nn: int = 2\nn += 1\n")
    for name in ("Board", "helper", "os", "Alias", "x", "y", "n"):
        assert import_hint(_err(name), tmp_path) == "", name


def test_no_error_outside_or_unreadable_module_adds_nothing(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    (ws / "pkg").mkdir(parents=True)
    (tmp_path / "secret.py").write_text(GO)
    (ws / "pkg" / "bad.py").write_text("def x(:\n")
    assert import_hint("all good", ws) == ""
    assert import_hint(_err("WHITE", "missing"), ws) == ""
    assert import_hint(_err("WHITE", "pkg.bad"), ws) == ""
    (ws / "link.py").symlink_to(tmp_path / "secret.py")
    assert import_hint(_err("WHITE", "link"), ws) == ""


async def test_the_hint_reaches_the_model(tmp_path: Path) -> None:
    (tmp_path / "go.py").write_text(GO)
    cmds = ["python3 -c 'from go import WHITE'", "ls"]
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
    assert "[hint] `WHITE` is defined inside `class Board` in go.py" in seen
