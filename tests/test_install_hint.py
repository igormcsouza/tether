"""The missing-package hint: a workspace venv instead of pip/apt guesses (gap hunt, pip task:
13 steps of `pip`, `apt-get` and `ensurepip` on a system Python without pip)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tether import harness
from tether.harness import install_hint

TRACE = "Traceback (most recent call last):\nModuleNotFoundError: No module named 'tabulate'\n"


def test_a_missing_package_gets_a_venv_hint_once(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(harness.shutil, "which", lambda _: "/u/bin/uv")
    shown: set[str] = set()
    hint = install_hint(TRACE, tmp_path, shown)
    assert "`tabulate` is not installed" in hint and "`uv venv && uv pip install tabulate`" in hint
    assert len(hint) < 200
    assert install_hint(TRACE, tmp_path, shown) == ""  # once per package


def test_without_uv_the_stdlib_venv_and_real_package_names(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(harness.shutil, "which", lambda _: None)
    hint = install_hint("No module named 'yaml.constructor'", tmp_path, set())
    assert "`python3 -m venv .venv && .venv/bin/pip install pyyaml`" in hint


@pytest.mark.parametrize(
    "out",
    ["bash: line 1: pip: command not found", "/usr/bin/python3: No module named pip",
     "error: externally-managed-environment"],
)  # fmt: skip
def test_no_pip_gets_the_hint(out: str, tmp_path: Path) -> None:
    assert "pip is not available here" in install_hint(out, tmp_path, set())


def test_workspace_modules_and_plain_output_get_none(tmp_path: Path) -> None:
    (tmp_path / "shop").mkdir()
    (tmp_path / "calc.py").write_text("")
    assert install_hint("No module named 'shop.pricing'", tmp_path, set()) == ""
    assert install_hint("No module named 'calc'", tmp_path, set()) == ""
    assert install_hint("all good", tmp_path, set()) == ""
