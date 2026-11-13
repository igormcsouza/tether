"""Unit tests for the sed -n quoted-path normalizer (#270)."""

from __future__ import annotations

import pytest

from tether.multiplexer import normalize_cmd


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("sed -n '45,90p tether/cli.py'", "sed -n '45,90p' tether/cli.py"),
        ('sed -n "45,90p tether/cli.py"', "sed -n '45,90p' tether/cli.py"),
        ("sed -n '12p f.py'", "sed -n '12p' f.py"),
        ("  sed -n '12p f'  ", "sed -n '12p' f"),
        ("```\nsed -n '12p f'\n```", "sed -n '12p' f"),
    ],
)
def test_quoted_path_is_moved_out_of_quotes(raw: str, expected: str) -> None:
    assert normalize_cmd(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "sed -n '45,90p' tether/cli.py",
        "sed -n '1,5p a.py b.py'",
        "sed -i 's/a/b/ f'",
        "sed -n '/x y/p' f",
        "sed -n '12p'",
        "sed -n '12p f.py' | head",
        "sed -n '12p f.py';ls",
        '''sed -n '12p f.py"''',
        "sed -n '12p my file.py'",
        "sed -n '12p a;rm'",
        "sed -n '12p f.py;ls'",
        "sed -n '12p f|x'",
        "sed -n '12p $(id)'",
        "sed -n '12p a&&rm'",
        "sed -n '12p `id`'",
        "sed -n '12p f>x'",
        "sed -n '12p f'x'",
        "sed -n '12p *.py'",
        "sed -n '12p -i'",
        "sed -n '12p ~/x'",
        "sed -n '\u0661\u0662p f.py'",
        "ls",
        "",
    ],
)
def test_other_commands_are_returned_unchanged(raw: str) -> None:
    assert normalize_cmd(raw) == raw
