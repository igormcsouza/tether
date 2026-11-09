"""--fold-after and MCP fold_after must be a positive integer (#205).

A value below 1 is rejected loudly: CLI exit 1 (EXIT_USAGE), MCP ToolError.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from tether import api
from tether.cli import main
from tether.harness import Harness

MSG = "--fold-after must be a positive integer"


@pytest.mark.parametrize("value", ["0", "-1"])
def test_cli_run_rejects_non_positive_fold_after(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], value: str
) -> None:
    code = main(["run", "--db", str(tmp_path / "t.db"), "--fold-after", value, "goal"])
    assert code == api.EXIT_USAGE
    assert MSG in capsys.readouterr().err


@pytest.mark.parametrize("value", [0, -1])
def test_harness_rejects_non_positive_fold_after(tmp_path: Path, value: int) -> None:
    with pytest.raises(ValueError, match=MSG):
        Harness(db_path=tmp_path / "t.db", fold_observations_after=value)


@pytest.mark.parametrize("value", [0, -1])
def test_mcp_rejects_non_positive_fold_after(tmp_path: Path, value: int) -> None:
    pytest.importorskip("mcp")
    from tether.mcp import TetherMCP, ToolError

    impl = TetherMCP(db_path=tmp_path / "t.db", workspace=tmp_path)
    with pytest.raises(ToolError, match=MSG):
        asyncio.run(impl.call("tether_run", {"goal": "g", "wait": False, "fold_after": value}))


def test_cli_pipeline_rejects_non_positive_fold_after(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest = tmp_path / "p.yaml"
    manifest.write_text("stages: []\n")
    code = main(
        ["pipeline", "--db", str(tmp_path / "t.db"), "--fold-after", "0", str(manifest), "goal"]
    )
    assert code == api.EXIT_USAGE
    assert MSG in capsys.readouterr().err


def test_declared_fold_after_below_one_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("tether.harness.load_declared", lambda: {"ollama": {"fold_after": 0}})
    with pytest.raises(ValueError, match=MSG):
        Harness(db_path=tmp_path / "t.db", model="ollama/x")
