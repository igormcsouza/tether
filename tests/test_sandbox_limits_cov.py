"""Fast coverage tests for --limit validation (no real processes run)."""

from __future__ import annotations

from typing import Any

import pytest

from tether import SandboxPolicy, cli
from tether.sandbox import LIMIT_MAX, parse_limits


def test_non_integer_limit_values_rejected() -> None:
    with pytest.raises(ValueError, match="whole number"):
        SandboxPolicy(limits={"cpu": 1.5})
    with pytest.raises(ValueError, match="whole number"):
        SandboxPolicy(limits={"mem": [1024]})


@pytest.mark.parametrize("spec", ["cpu=abc", "cpu=0"])
def test_cli_pipeline_invalid_limit_exits_1(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], spec: str
) -> None:
    def no_harness(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("Harness must not be built for an invalid --limit")

    monkeypatch.setattr(cli, "Harness", no_harness)
    assert cli.main(["pipeline", "--limit", spec, "p.yaml", "goal"]) == cli.EXIT_USAGE == 1
    assert "Error: --limit:" in capsys.readouterr().err


def test_bare_string_is_one_item() -> None:
    assert parse_limits("cpu=1") == {"cpu": 1}
    with pytest.raises(ValueError, match="limit 'cpu': expected K=V"):
        parse_limits("cpu")


@pytest.mark.parametrize("raw", [{"cpu": 10**30}, ["fsize=99999999999999"]])
def test_huge_values_rejected(raw: Any) -> None:
    with pytest.raises(ValueError, match="too large"):
        parse_limits(raw)
    assert parse_limits({"cpu": LIMIT_MAX}) == {"cpu": LIMIT_MAX}


def test_integral_float_rejected() -> None:
    with pytest.raises(ValueError, match="whole number"):
        parse_limits({"cpu": 1.0})


def test_cli_other_policy_error_not_labelled_limit(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def bad_policy(*args: Any, **kwargs: Any) -> None:
        raise ValueError("Unsupported sandbox profile: x")

    monkeypatch.setattr(cli, "SandboxPolicy", bad_policy)
    assert cli.main(["run", "task"]) == 1
    err = capsys.readouterr().err
    assert "Error: Unsupported sandbox profile: x" in err
    assert "--limit" not in err
