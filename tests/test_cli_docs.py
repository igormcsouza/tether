"""The CLI reference page documents every subcommand and every flag (#61)."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from tether.cli import build_parser

DOC = Path(__file__).resolve().parents[1] / "docs" / "reference" / "cli.md"
ROOT = Path(__file__).resolve().parents[1]


def _subparsers() -> dict[str, argparse.ArgumentParser]:
    parser = build_parser()
    action = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    return {name: sp for name, sp in action.choices.items() if not name.startswith("_")}


def _sections() -> dict[str, str]:
    parts = re.split(r"^## ", DOC.read_text(), flags=re.MULTILINE)[1:]
    return {p.splitlines()[0].strip().strip("`"): p for p in parts}


def test_every_subcommand_has_a_section() -> None:
    assert set(_subparsers()) <= {k.removeprefix("tether ") for k in _sections()}


def test_every_flag_is_documented_in_its_section() -> None:
    sections = {k.removeprefix("tether "): v for k, v in _sections().items()}
    missing = [
        f"{name} {flag}"
        for name, sp in _subparsers().items()
        for action in sp._actions
        for flag in action.option_strings
        if flag.startswith("--") and flag != "--help" and flag not in sections.get(name, "")
    ]
    assert not missing, f"undocumented flags: {missing}"


def test_exit_codes_and_nav() -> None:
    text = DOC.read_text()
    for code in ("`0`", "`1`", "`2`", "`3`", "`4`", "`5`"):
        assert code in text
    assert "reference/cli.md" in (ROOT / "mkdocs.yml").read_text()
