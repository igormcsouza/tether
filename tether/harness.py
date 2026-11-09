"""Control Plane: Tether Harness, bounded agent loop, live SQLite inbox, and headless spawner."""

from __future__ import annotations

import ast
import asyncio
import dataclasses
import os
import re
import subprocess
import sys
import time
import traceback
import uuid
from collections import Counter
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from typing import Any

import yaml

from tether.context import (
    ACT_TOOL_SCHEMA,
    DEFAULT_CONTEXT_TOKENS,
    MAX_RESTARTS,
    RESTART_AFTER_FAILS,
    ContextAssembler,
    after_restart,
    describe_attempts,
    estimate_messages_tokens,
    live_read_obs,
    modified_files,
    restart_message,
)
from tether.decorator import ToolSpec, build_tool_spec
from tether.gates import precheck as gates_precheck
from tether.multiplexer import Multiplexer, normalize_cmd
from tether.pipeline import Pipeline, load_pipeline, parse_pipeline_yaml, render_stage_goal
from tether.providers import ModelProvider, resolve_provider
from tether.providers.base import ProviderError
from tether.providers.declarative import load_declared
from tether.sandbox import SandboxPolicy, SandboxUnavailableError
from tether.schema import validate_output
from tether.skills import Skill, SkillLoader, make_skill_tool
from tether.store import SessionRecord, SQLiteStore, sandbox_rule, worker_log_path
from tether.tools import (
    ALL_BUILTIN_TOOLS,
    make_agent_tool,
    make_bash_tool,
    make_done_tool,
    make_edit_tool,
    make_mem_tool,
    make_web_tool,
)
from tether.trace import NEAR_PASS, failing_test_id, runtime_trace, smallest_failing
from tether.unchanged import (
    arg_snapshot,
    missing_targets,
    small_change_note,
    snapshot,
    snapshot_key,
    unchanged_note,
    whole_file_targets,
)
from tether.worktree import commit_all, create_worktree, repo_root, run_setup


def detect_cycle(history: list[tuple[str, str | None]], window: int = 8) -> list[str] | None:
    """Repeated n-gram at the tail of the last `window` actions, else None.

    A 2-gram must repeat 3 times, a 3-gram or 4-gram 2 times, so a legitimate
    `test / view / test / view` pair is not flagged. Identical-command runs are
    `loop_stall`'s job, so they are not a cycle here.
    """
    recent = history[-window:]
    for n, reps in ((2, 3), (3, 2), (4, 2)):
        tail = recent[-n:]
        if len(recent) >= n * reps and recent[-n * reps :] == tail * reps and len(set(tail)) > 1:
            return [cmd for cmd, _ in tail]
    return None


# Stall guard: warn after N reads of one file with varying ranges, abort after M warnings
# A provider call that fails after its own retries is tried once more at turn level (0 prompt
# tokens) after TETHER_OUTAGE_BACKOFF (default 10) seconds; a second failure in a row ends the
# session (#147: a hung endpoint cost up to 12 timeouts before).
OUTAGE_RETRIES = 1
RANGE_STALL_READS = 7  # after the 6-step quiet [NUDGE], which gets the first word
STALL_ABORT = 4
# A plain-text reply this long may be the answer: it is kept and the model told it was not
# delivered (#173); a stuck hand-back carries the last one, bounded
PROSE_ANSWER_CHARS = 80
KEPT_REPLY_CHARS = 2000
_READERS = {"cat", "head", "tail", "grep", "rg", "sed", "wc", "awk", "gawk", "mawk"}


def read_target(cmd: str) -> str | None:
    """File a read-only command inspects (`edit view p`, `sed -n 1,9p p`, `cat p`), else None."""
    argv = cmd.split()
    argv = argv[1:] if argv[:1] == ["bash"] else argv
    if argv[:2] == ["edit", "view"] and len(argv) > 2:
        return argv[2]
    if argv[:1] and argv[0] in _READERS and is_quiet(cmd):
        paths = [a for a in argv[1:] if not a.startswith("-") and ("." in a or "/" in a)]
        return paths[-1] if paths else None
    return None


# Quiet nudge: completion hint after N consecutive read-only/verification steps following a
# change, repeated every QUIET_NUDGE_EVERY quiet steps (#132)
QUIET_NUDGE_STEPS = 6
QUIET_NUDGE_EVERY = 8
# Steps-left hint (#133): once, at 75% of the step limit, for limits of at least 8 steps
STEPS_LEFT_MIN = 8
# Exploration nudge (#127): same hint when nothing was changed yet, first at 12 quiet steps,
# then every 8 more while the model keeps only reading.
EXPLORE_NUDGE_STEPS = 12
EXPLORE_NUDGE_EVERY = 8
_QUIET = {"cat", "head", "tail", "grep", "rg", "ls", "find", "wc", "pytest", "ruff", "mypy"}


_WRITES = re.compile(
    r"(?:^|[^<>&\d\s])\s*>{1,2}(?![=\d])\s*[^&\s]|\d>{1,2}\s*[^&\s]|\b(?:open|write|write_text|write_bytes|"
    r"unlink|remove|rmtree|rename|replace|system|Popen|touch|mkdir|sed\s+-i|tee)\b"
)
_AWK = ("awk", "gawk", "mawk")
# awk is read-only unless it prints to a file, pipes to a shell or edits in place; `NR>=5` is a test
_AWK_WRITES = re.compile(
    r"\bprintf?\b[^;}|]*>|\bsystem\s*\(|\|\s*[\"']?\s*(?:sh|bash|tee)\b|inplace"
)
_PY = ("python", "python3")
_PY_TESTS = (["-m", "unittest"], ["-m", "pytest"], ["-m", "doctest"])


_TEST_CMD = re.compile(
    r"\b(pytest|unittest|go test|cargo test|npm (?:run )?test|make test|jest|mocha)\b"
)
_TESTS_RED = re.compile(r"\[exit [1-9]\d*\]|\b(FAILED|FAIL|Error|Traceback)\b|\bfailed\b")
_TESTS_GREEN = re.compile(r"^OK\b|\b\d+ passed\b|^ok\s", re.M)


def tests_green(cmd: str, out: str) -> bool:
    """True when `cmd` is a test runner whose output reports success (#177)."""
    return bool(_TEST_CMD.search(cmd) and _TESTS_GREEN.search(out) and not _TESTS_RED.search(out))


_TRACE_FRAME = re.compile(r'File "([^"]+)", line (\d+), in (\w+)')


def failing_test_source(out: str, root: Path) -> str:
    """Source of the failing test functions named in a traceback, inside `root` (#173)."""
    base = root.resolve()
    seen: set[tuple[str, str]] = set()
    parts: list[str] = []
    for raw, line_s, name in _TRACE_FRAME.findall(out):
        if not name.startswith("test") or not raw.endswith(".py"):
            continue
        path = Path(raw) if Path(raw).is_absolute() else root / raw
        resolved = path.resolve()
        if not resolved.is_relative_to(base) or (str(resolved), name) in seen:
            continue
        seen.add((str(resolved), name))
        try:
            text = resolved.read_text(encoding="utf-8")
            tree = ast.parse(text)
        except (OSError, SyntaxError, ValueError):
            continue
        lines = text.splitlines()
        line = int(line_s)
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            end = node.end_lineno or node.lineno
            if node.name != name or not node.lineno <= line <= end:
                continue
            if lines[node.lineno - 1].strip() in out:
                break
            body = "\n".join(lines[node.lineno - 1 : end])[:600]
            part = f"# {resolved.relative_to(base).as_posix()}:{node.lineno}\n{body}"
            if len(parts) < 3 and len("\n".join([*parts, part])) <= 1475:
                parts.append(part)
            break
    if not parts:
        return ""
    return "\n[failing test source]\n" + "\n".join(parts)


_UNITTEST_RAN = re.compile(r"Ran (\d+) tests?")
_UNITTEST_FAIL = re.compile(r"^(?:FAIL|ERROR): (\w+) \(", re.M)
_PYTEST_COUNT = re.compile(r"(\d+) (?:passed|failed|errors?)\b")
_UNITTEST_SUMMARY = re.compile(r"^FAILED \(([^)]*)\)", re.M)
_PYTEST_FAIL = re.compile(r"^(?:FAILED|ERROR) \S*::(\w+)", re.M)


def run_outcome(out: str) -> tuple[int, frozenset[str]] | None:
    """Tests run and failing test names from a unittest or pytest summary, else None (#173)."""
    if ran := _UNITTEST_RAN.search(out):
        return int(ran.group(1)), frozenset(_UNITTEST_FAIL.findall(out))
    counts = _PYTEST_COUNT.findall(out)
    if not counts:
        return None
    return sum(map(int, counts)), frozenset(_PYTEST_FAIL.findall(out))


def failing_count(out: str, names: frozenset[str]) -> int:
    """Failing tests by the summary line (`FAILED (failures=1, errors=2)`, `3 failed`), so a run cut
    by `head` that names only a few still counts them all; at least `len(names)`."""
    if summary := _UNITTEST_SUMMARY.search(out):
        counts = re.findall(r"(?:failures|errors)=(\d+)", summary.group(1))
    else:
        counts = re.findall(r"(\d+) (?:failed|errors?)\b", out)
    return max(len(names), sum(map(int, counts)))


def regression_note(before: tuple[int, frozenset[str]], after: tuple[int, frozenset[str]]) -> str:
    """Note naming the tests the last change broke, when both runs are comparable (#173)."""
    if before[0] != after[0] or not (broke := sorted(after[1] - before[1])):
        return ""
    fixed = sorted(before[1] - after[1])

    def listed(names: list[str]) -> str:
        more = f" (+{len(names) - 5} more)" if len(names) > 5 else ""
        return ", ".join(names[:5]) + more

    note = (
        f"\n[regression] Your last change broke {len(broke)} test(s) that passed before: "
        f"{listed(broke)}"
    )
    if fixed:
        note += f"; now passing: {listed(fixed)}"
    return (note + ". Keep what worked.")[:400]


_NOISE = re.compile(r"&>\s*/dev/null|\d?>>?\s*/dev/null|\d>&\d")
_STATEMENT = re.compile(r"""(?:"[^"]*"|'[^']*'|[^;&|\n"'])+""")
_BLOCK_OPEN = re.compile(r"^(?:(?:do|then|else|elif|if|while|until)\b\s*)+")
_BLOCK_END = ("done", "fi", "esac")
_QUIET_ONLY = _QUIET | {"echo", "pwd", "which", "cd", "true", "stat", "diff", "sort", "tree"}
# Built-in tool verbs that only look things up
_LOOKUPS = [
    ["web", "search"],
    ["web", "fetch"],
    ["mem", "search"],
    ["mem", "recall"],
    *(["agent", v] for v in ("status", "wait", "read", "query")),
]


def suite_for(rel: str, root: Path, since: float) -> str | None:
    """The test file next to `rel` (`x_test.py` or `test_x.py`) when `rel` existed at `since`."""
    path = root / rel
    stem = path.stem
    if stem.startswith("test_") or stem.endswith("_test"):
        return None
    try:
        if path.stat().st_mtime >= since:
            return None
    except OSError:
        return None
    # ponytail: Python test names only; other languages are written at once
    for name in (f"{stem}_test.py", f"test_{stem}.py"):
        if (path.parent / name).is_file():
            return os.path.normpath(str(Path(rel).parent / name))
    return None


def suite_read(cmd: str, root: Path, since: float) -> tuple[str, str] | None:
    """(starting file, its test file) when `cmd` names the test file of a starting file."""
    for word in re.findall(r"[\w./-]+\.py\b", cmd):
        test = Path(word)
        src = str(test.with_name(test.stem.removeprefix("test_").removesuffix("_test") + ".py"))
        if src != word and suite_for(src, root, since) == os.path.normpath(word):
            return os.path.normpath(src), os.path.normpath(word)
    return None


def is_quiet(cmd: str) -> bool:
    """True if every statement of `cmd` is read-only or a verification (`for f in x; do cat`)."""
    stmts = []
    for stmt in _STATEMENT.findall(_NOISE.sub("", cmd)):
        stmt = _BLOCK_OPEN.sub("", stmt.strip().removeprefix("bash "))
        if stmt and stmt not in _BLOCK_END and not stmt.startswith("for "):
            stmts.append(stmt)
    return bool(stmts) and all(_quiet_statement(s) for s in stmts)


def _quiet_statement(cmd: str) -> bool:
    argv = cmd.split()
    if argv[0] in _AWK:
        return not _AWK_WRITES.search(cmd)
    if _WRITES.search(cmd):
        return False
    if argv[0] in _PY and (
        argv[1:2] == ["-c"]
        or argv[1:2] == ["-m"]
        and argv[2:3] in (["unittest"], ["pytest"], ["doctest"])
    ):
        return True
    if argv[0] in _QUIET_ONLY:
        return True
    if argv[:2] == ["edit", "view"] or argv[:2] in _LOOKUPS:
        return True
    if argv[0] == "git" and argv[1:2] in (["diff"], ["log"], ["status"], ["show"]):
        return True
    if argv[0] == "sed" and "-n" in argv:
        return True
    return False


def spawn_detached_worker(db_path: Path, session_id: str) -> int:
    """Spawn a detached OS background worker (`python -P -m tether.cli _worker <session_id>`).
    # -P: cwd must never shadow the installed tether (#273)
    """
    env = dict(os.environ)
    env["TETHER_DB"] = str(db_path)
    log = worker_log_path(db_path, session_id)
    log.parent.mkdir(parents=True, exist_ok=True)
    # Keep the worker's output: a worker that dies before RUNNING leaves its cause here (#271)
    with log.open("ab") as out:
        proc = subprocess.Popen(
            [sys.executable, "-P", "-m", "tether.cli", "_worker", session_id, "--db", str(db_path)],
            stdin=subprocess.DEVNULL,
            stdout=out,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            env=env,
        )
    return proc.pid


class PipelineResumeError(ValueError):
    """A pipeline session cannot be resumed; the CLI reports it as a usage error."""


_STAGE_TURN_RE = re.compile(r"^stage (.+) \(([^()]+)\)$")


def _tokens_used(rec: SessionRecord) -> int:
    return rec.total_prompt_tokens + rec.total_completion_tokens


def _token_budget_text(used: int, budget: int, steps: int) -> str:
    return f"[TOKEN BUDGET] used {used} of {budget} tokens after {steps} steps"


class Harness:
    """General-purpose LLM-Native Micro-Harness.

    `output_schema` (JSON Schema subset) is a deterministic pre-`done` gate: the deliverable
    must be JSON matching it. `tether.api.failure_info` classifies FAILED results by the
    prefixes "Verification gate", "Stopped" and "Worker error".
    """

    def __init__(
        self,
        *,
        model: str | None = None,
        tools: list[str | ToolSpec | Callable[..., Any]] | str | None = None,
        skill: str | Skill | None = None,
        verify: list[str] | str | None = None,
        max_verify_failures: int = 3,
        sandbox: SandboxPolicy | None = None,
        db_path: str | Path | None = None,
        max_steps: int = 15,
        max_tokens: int | None = None,
        max_context_tokens: int | None = None,
        fold_observations_after: int | None = None,
        provider: ModelProvider | None = None,
        skill_search_dirs: list[str | Path] | None = None,
        worker_spawner: Callable[[str], int | None] | None = None,
        output_schema: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        worktree: bool = False,
        worktree_from: str | None = None,
        setup: str | None = None,
        allow_unsandboxed: bool = False,
    ) -> None:
        if max_tokens is not None and max_tokens <= 0:
            raise ValueError(f"--max-tokens must be a positive integer (got {max_tokens}).")
        if fold_observations_after is not None and fold_observations_after < 1:
            raise ValueError(
                f"--fold-after must be a positive integer (got {fold_observations_after})."
            )
        self.model = model or os.environ.get("TETHER_MODEL") or "ollama/qwen3.5:9b"
        self.store = SQLiteStore(db_path=db_path)
        self.sandbox = sandbox or SandboxPolicy()
        if allow_unsandboxed:  # never mutate the caller's policy object
            self.sandbox = dataclasses.replace(self.sandbox, allow_unsandboxed=True)
        self.max_steps = max_steps
        self.worktree = worktree
        self.worktree_from = worktree_from
        self.setup = setup
        self.max_tokens = max_tokens
        self.max_verify_failures = max_verify_failures
        declared: dict[str, Any] = {}
        try:
            declared = load_declared().get(self.model.split("/")[0], {})
        except ValueError:
            declared = {}
        self.max_context_tokens: int = int(
            max_context_tokens or declared.get("context_tokens") or DEFAULT_CONTEXT_TOKENS
        )
        # No explicit K (flag, providers.yaml or MCP): fold only as far as the window needs (#205).
        explicit_fold = (
            fold_observations_after
            if fold_observations_after is not None
            else declared.get("fold_after")
        )
        self.auto_fold = explicit_fold is None
        self.fold_observations_after: int = int(explicit_fold) if explicit_fold is not None else 2
        if self.fold_observations_after < 1:
            raise ValueError(
                f"--fold-after must be a positive integer (got {self.fold_observations_after})."
            )
        self._provider = provider
        self.skill_loader = SkillLoader(search_dirs=skill_search_dirs)
        self._worker_spawner = worker_spawner
        self.output_schema = output_schema
        self.params = dict(params or {})

        self._custom_tools: dict[str, ToolSpec] = {}
        self._enabled_tool_names: list[str] = []
        self._verify_commands: list[str] = []

        if isinstance(skill, Skill):
            self._skill: Skill | None = skill
            self.skill_name: str | None = skill.name
        elif isinstance(skill, str) and skill.strip():
            self.skill_name = skill.strip()
            self._skill = self.skill_loader.load(self.skill_name)
        else:
            self._skill = None
            self.skill_name = None

        if self._skill:
            if model is None and self._skill.model:
                self.model = self._skill.model
            for ct in self._skill.custom_tools:
                self._custom_tools[ct.name] = ct
            for vcmd in self._skill.verify:
                if vcmd not in self._verify_commands:
                    self._verify_commands.append(vcmd)

        if verify is not None:
            raw_verify = [verify] if isinstance(verify, str) else list(verify)
            for v in raw_verify:
                v_clean = v.strip()
                if v_clean and v_clean not in self._verify_commands:
                    self._verify_commands.append(v_clean)

        for sv in self.sandbox.verify_commands:
            if sv not in self._verify_commands:
                self._verify_commands.append(sv)
        self.sandbox.verify_commands = list(self._verify_commands)

        self._configure_initial_tools(tools)

    def _configure_initial_tools(
        self, tools: list[str | ToolSpec | Callable[..., Any]] | str | None
    ) -> None:
        raw_items: list[str | ToolSpec | Callable[..., Any]] = []
        if tools is None:
            if self._skill and self._skill.tools:
                raw_items.extend(self._skill.tools)
        elif isinstance(tools, str):
            for part in tools.split(","):
                if part.strip():
                    raw_items.append(part.strip())
        else:
            raw_items.extend(tools)

        for item in raw_items:
            if isinstance(item, str):
                name = item.strip()
                if name == "all":
                    for b in ALL_BUILTIN_TOOLS:
                        if b not in self._enabled_tool_names:
                            self._enabled_tool_names.append(b)
                elif name and name != "done" and name not in self._enabled_tool_names:
                    self._enabled_tool_names.append(name)
            else:
                self.register(item)

        unknown = [
            n
            for n in self._enabled_tool_names
            if n not in ALL_BUILTIN_TOOLS and n not in self._custom_tools
        ]
        if unknown:
            self.store.close()
            raise ValueError(
                f"Unknown tool(s): {', '.join(unknown)}. "
                f"Valid: {', '.join(ALL_BUILTIN_TOOLS)}, or a registered custom/skill tool."
            )

    def register(self, fn_or_spec: ToolSpec | Callable[..., Any]) -> ToolSpec:
        """Register a custom Python function or ToolSpec with this Harness."""
        if isinstance(fn_or_spec, ToolSpec):
            spec = fn_or_spec
        elif hasattr(fn_or_spec, "__tether_tool__"):
            spec = fn_or_spec.__tether_tool__
        else:
            spec = build_tool_spec(fn_or_spec)
        self._custom_tools[spec.name] = spec
        if spec.name not in self._enabled_tool_names:
            self._enabled_tool_names.append(spec.name)
        return spec

    def _spawner_for_store(self) -> Callable[[str], int | None]:
        if self._worker_spawner is not None:
            return self._worker_spawner

        def _default_spawn(session_id: str) -> int | None:
            pid = spawn_detached_worker(self.store.db_path, session_id)
            self.store.update_session(session_id, pid=pid)
            return pid

        return _default_spawn

    def build_multiplexer(
        self,
        session_id: str,
        enabled_tools: list[str],
        sandbox: SandboxPolicy,
        model: str,
    ) -> Multiplexer:
        """Construct the session Multiplexer with `done` + strictly opted-in tools."""
        mux = Multiplexer()
        # `done` is always registered first
        mux.register(make_done_tool())

        names_to_load: list[str] = []
        for t in enabled_tools:
            if t == "all":
                for b in ALL_BUILTIN_TOOLS:
                    if b not in names_to_load:
                        names_to_load.append(b)
            elif t != "done" and t not in names_to_load:
                names_to_load.append(t)

        for name in names_to_load:
            if name in self._custom_tools:
                mux.register(self._custom_tools[name])
            elif name == "bash":
                mux.register(make_bash_tool(sandbox))
            elif name == "edit":
                mux.register(make_edit_tool(sandbox))
            elif name == "web":
                mux.register(make_web_tool(web_allow=sandbox.web_allow))
            elif name == "mem":
                mux.register(make_mem_tool(self.store, session_id))
            elif name == "skill":
                mux.register(make_skill_tool(self.skill_loader, mux))
            elif name == "agent":
                mux.register(
                    make_agent_tool(
                        store=self.store,
                        parent_session_id=session_id,
                        default_model=model,
                        parent_sandbox=sandbox,
                        skill_loader=self.skill_loader,
                        worker_spawner=self._spawner_for_store(),
                    )
                )
        return mux

    @staticmethod
    def _resolve_pipeline(
        pipeline: Pipeline | str | Path | dict[str, Any],
    ) -> Pipeline:
        if isinstance(pipeline, Pipeline):
            return pipeline
        if isinstance(pipeline, dict):
            return Pipeline.from_dict(pipeline)
        if isinstance(pipeline, Path):
            return load_pipeline(pipeline)
        raw_str = str(pipeline).strip()
        if "\n" in raw_str or raw_str.startswith("stages:"):
            return parse_pipeline_yaml(raw_str)
        return load_pipeline(Path(raw_str))

    def create_pipeline_session(
        self,
        pipeline: Pipeline | str | Path | dict[str, Any],
        goal: str,
        *,
        parent_id: str | None = None,
    ) -> SessionRecord:
        """Create a persisted root pipeline session row in SQLite without executing it yet."""
        resolved = self._resolve_pipeline(pipeline)
        root_sandbox = self.sandbox.attenuate(resolved.sandbox)
        for stage in resolved.stages:  # only stages that still write need bwrap
            root_sandbox.attenuate(stage.sandbox).require_isolation()
        sbox_dict = root_sandbox.to_dict()
        sbox_dict["sandbox_mode"] = root_sandbox.mode()
        sbox_dict["pipeline"] = resolved.to_dict()
        if isinstance(pipeline, Path):
            sbox_dict["pipeline_source"] = str(pipeline.resolve())
        # The row's model may list several; keep the default for model-less stages.
        sbox_dict["pipeline_model"] = self.model
        models: list[str] = []
        for stage in resolved.stages:
            skill_obj = self.skill_loader.load(stage.skill) if stage.skill else None
            stage_model = stage.model or (skill_obj and skill_obj.model) or self.model
            if stage_model not in models:
                models.append(stage_model)
        return self.store.create_session(
            goal=goal,
            model=",".join(models),
            skill=resolved.name,
            tools=self._enabled_tool_names,
            sandbox_config=sbox_dict,
            parent_id=parent_id,
            max_steps=len(resolved.stages),
        )

    def spawn_pipeline(
        self,
        pipeline: Pipeline | str | Path | dict[str, Any],
        goal: str,
        *,
        parent_id: str | None = None,
    ) -> str:
        """Create a pipeline session and launch it as a detached headless worker."""
        rec = self.create_pipeline_session(pipeline, goal, parent_id=parent_id)
        spawner = self._spawner_for_store()
        spawner(rec.id)
        return rec.id

    async def run_pipeline(
        self,
        pipeline: Pipeline | str | Path | dict[str, Any],
        goal: str,
        *,
        parent_id: str | None = None,
    ) -> SessionRecord:
        """Execute a deterministic multi-stage pipeline with isolated stage sessions."""
        rec = self.create_pipeline_session(pipeline, goal, parent_id=parent_id)
        return await self.execute_session(rec.id)

    async def resume_pipeline(self, session_id: str) -> SessionRecord:
        """Re-run a failed or waiting pipeline from its first stage that is not COMPLETED."""
        rec = self.store.get_session(session_id)
        if rec is None:
            raise PipelineResumeError(
                f"pipeline session `{session_id}` not found. "
                "Use the id printed by `tether pipeline --headless`."
            )
        raw_pipe = rec.sandbox_config.get("pipeline")
        if not isinstance(raw_pipe, dict):
            raise PipelineResumeError(f"session `{session_id}` is not a pipeline.")
        if rec.status == "RUNNING":
            raise PipelineResumeError(
                f"pipeline `{session_id}` is RUNNING (pid {rec.pid}). "
                "Wait for it to finish, then resume."
            )
        if rec.status == "COMPLETED":
            return rec
        try:
            pipeline = Pipeline.from_dict(raw_pipe)
        except (KeyError, TypeError, ValueError) as exc:
            raise PipelineResumeError(
                f"cannot resume pipeline `{session_id}`: stored pipeline is invalid: {exc}"
            ) from exc
        source = rec.sandbox_config.get("pipeline_source")
        reason = ""
        if not source:
            reason = "no stored manifest path (the run predates --resume)"
        else:
            try:
                Pipeline.load(str(source))
            except FileNotFoundError:
                reason = f"manifest `{source}` not found"
            except (OSError, ValueError, yaml.YAMLError) as exc:
                reason = f"manifest `{source}` is invalid: {exc}"
        if reason:
            raise PipelineResumeError(
                f"cannot resume pipeline `{session_id}`: {reason}. "
                "Re-run with `tether pipeline <file> <goal>`."
            )
        prefix = self._completed_prefix(rec, pipeline)
        return await self._execute_pipeline_session(rec, prior=prefix)

    def create_session(self, goal: str, *, parent_id: str | None = None) -> SessionRecord:
        """Create a persisted session row in SQLite without executing it yet."""
        self.sandbox.require_isolation()  # before the worktree, the row and any model call
        sbox_dict = self.sandbox.to_dict()
        sbox_dict["sandbox_mode"] = self.sandbox.mode()
        if self.output_schema:
            sbox_dict["output_schema"] = self.output_schema
        if self.params:
            sbox_dict["params"] = self.params
        session_id: str | None = None
        if self.worktree:
            session_id = f"ses_{uuid.uuid4().hex[:8]}"
            path, branch = create_worktree(repo_root(Path.cwd()), session_id, self.worktree_from)
            sbox_dict.update(
                worktree=str(path), branch=branch, commit=None, workspace_root=str(path)
            )
        rec = self.store.create_session(
            goal=goal,
            model=self.model,
            skill=self.skill_name,
            tools=self._enabled_tool_names,
            sandbox_config=sbox_dict,
            parent_id=parent_id,
            max_steps=self.max_steps,
            session_id=session_id,
            max_tokens=self.max_tokens,
            token_grant=self.max_tokens,
        )
        if self.worktree and self.setup:
            error = run_setup(path, self.setup)
            if error:
                sbox_dict["setup_failed"] = True
                self.store.set_sandbox_config(rec.id, sbox_dict)
                self.store.update_session(rec.id, status="FAILED", result=error)
                return self.store.get_session(rec.id) or rec
        return rec

    @classmethod
    def from_session(
        cls,
        rec: SessionRecord,
        *,
        db_path: str | Path | None = None,
        model: str | None = None,
        max_steps: int | None = None,
        worktree: bool = False,
        worktree_from: str | None = None,
        setup: str | None = None,
    ) -> Harness:
        """Rebuild a harness from a stored session (used by `tether replay`).

        Runs in the current directory (the stored workspace_root is not reused).
        Verify gates are not stored, so they are not restored.
        With worktree=True the replay runs in its own git worktree (worktree_from sets
        the base ref). setup is a shell command run in that worktree before the model starts.
        """
        cfg = dict(rec.sandbox_config)
        output_schema = cfg.pop("output_schema", None)
        params = cfg.pop("params", None)
        cfg.pop("workspace_root", None)
        return cls(
            model=model or rec.model,
            tools=list(rec.tools),
            skill=rec.skill,
            sandbox=SandboxPolicy.from_dict(cfg),
            db_path=db_path,
            max_steps=rec.max_steps if max_steps is None else max_steps,
            output_schema=output_schema,
            params=params,
            worktree=worktree,
            worktree_from=worktree_from,
            setup=setup,
        )

    def spawn(self, goal: str, *, parent_id: str | None = None) -> str:
        """Create a session and launch it as a detached headless worker, returning session_id."""
        rec = self.create_session(goal, parent_id=parent_id)
        spawner = self._spawner_for_store()
        spawner(rec.id)
        return rec.id

    async def run(self, goal: str, *, parent_id: str | None = None) -> SessionRecord:
        """Create and run a session inline until completion (`done`) or `max_steps`."""
        rec = self.create_session(goal, parent_id=parent_id)
        return await self.execute_session(rec.id)

    async def send(
        self,
        session_id: str,
        message: str,
        *,
        headless: bool = False,
    ) -> SessionRecord:
        """Send a message to SQLite inbox; auto-resumes if WAITING_INPUT/COMPLETED/FAILED."""
        rec = self.store.get_session(session_id)
        if not rec:
            raise ValueError(f"Session `{session_id}` not found.")

        self.store.enqueue_inbox(session_id, message)
        if rec.status == "RUNNING":
            return rec

        # Session was WAITING_INPUT/IDLE/COMPLETED/FAILED -> resume it
        # Extend max_steps if the session exhausted its budget (step_count == max_steps).
        # For a paused session (e.g. WAITING_INPUT at 5/40), keep remaining budget.
        new_max = max(rec.max_steps, rec.step_count + self.max_steps)
        self.store.update_session(session_id, max_steps=new_max)
        if rec.token_grant:
            cap = max(rec.max_tokens or 0, _tokens_used(rec)) + rec.token_grant
            self.store.update_session(session_id, max_tokens=cap)

        if headless:
            self.store.update_session(session_id, status="PENDING")
            spawner = self._spawner_for_store()
            spawner(session_id)
            updated = self.store.get_session(session_id)
            assert updated is not None
            return updated

        return await self.execute_session(session_id)

    async def _finished_by_harness(
        self,
        sandbox: SandboxPolicy,
        verify_commands: list[str],
        green_cmd: str | None,
        changed: bool,
    ) -> str | None:
        """Why an unfinished session counts as done, or None (#163, #177).

        The caller's `verify` gates decide when there are any. Otherwise the model's own last
        passing test run is the gate, if nothing changed since and it still passes now.
        """
        if not changed:
            return None
        if verify_commands:
            if await self._run_verification_gates(sandbox, verify_commands) is not None:
                return None
            return (
                "Finished by the harness: the model stopped calling tools after "
                "its change and every verification gate passes."
            )
        if green_cmd is None:
            return None
        argv = green_cmd.split()
        cmd = " ".join(argv[1:]) if argv[:1] == ["bash"] else green_cmd
        try:
            code, out = await sandbox.execute_bash_with_code(cmd)
        except Exception:
            return None
        if code != 0 or not tests_green(cmd, out):
            return None
        return (
            f"Finished by the harness: the model stopped calling tools after `{cmd[:60]}` "
            "passed on its last change."
        )

    async def _unfinished_result(
        self,
        head: str,
        sandbox: SandboxPolicy,
        verify_commands: list[str],
        changes: list[str],
    ) -> str:
        """A session ending without `done` still reports what it did and where it stands (#171)."""
        if not changes:
            return f"{head} No change was made."
        shown = "; ".join(f"`{c.splitlines()[0][:60]}`" for c in changes[-5:])
        text = f"{head} Changed: {shown} ({len(changes)} change commands)."
        if verify_commands:
            failure = await self._run_verification_gates(sandbox, verify_commands, 400)
            if failure is not None:
                text += f" Gate `{failure[0]}` fails (exit {failure[1]}):\n{failure[2]}"
        return text

    async def _run_verification_gates(
        self,
        sandbox: SandboxPolicy,
        verify_commands: list[str],
        max_gate_output_chars: int = 2000,
    ) -> tuple[str, int, str, bool] | None:
        """Run gates in order; return (cmd, code, output, is_error) on the first problem.

        `is_error` means the gate itself is broken (sandbox violation, command not found,
        timeout), not that the agent's work was rejected.
        """
        for vcmd in verify_commands:
            is_error = False
            try:
                code, out = await sandbox.execute_bash_with_code(vcmd)
                is_error = code in (124, 126, 127)
            except Exception as exc:
                code, out, is_error = 1, str(exc), True

            if code != 0:
                compact_out = out.strip()
                if len(compact_out) > max_gate_output_chars:
                    half = max_gate_output_chars // 2
                    omitted = len(compact_out) - max_gate_output_chars
                    compact_out = (
                        f"{compact_out[:half]}\n"
                        f"... [truncated {omitted:,} chars] ...\n"
                        f"{compact_out[-half:]}"
                    )
                return vcmd, code, compact_out, is_error
        return None

    def _completed_prefix(
        self, rec: SessionRecord, pipeline: Pipeline
    ) -> list[tuple[str, SessionRecord]]:
        """Return the leading stages whose latest tool turn recorded a COMPLETED child session."""
        done: dict[str, SessionRecord] = {}
        for turn in self.store.get_turns(rec.id):
            match = _STAGE_TURN_RE.match(turn.tool_cmd or "")
            if match is None or turn.event_type != "completed":
                continue
            child = self.store.get_session(match.group(2))
            if child is not None:
                done[match.group(1)] = child
        prefix: list[tuple[str, SessionRecord]] = []
        for stage in pipeline.stages:
            child = done.get(stage.id)
            if child is None:
                break
            prefix.append((stage.id, child))
        return prefix

    async def _execute_pipeline_session(
        self, rec: SessionRecord, prior: list[tuple[str, SessionRecord]] | None = None
    ) -> SessionRecord:
        """Execute a deterministic multi-stage pipeline with isolated child sessions."""
        raw_pipe = rec.sandbox_config.get("pipeline")
        assert isinstance(raw_pipe, dict)
        pipeline = Pipeline.from_dict(raw_pipe)
        root_sandbox = SandboxPolicy.from_dict(rec.sandbox_config)

        self.store.update_session(rec.id, status="RUNNING", pid=os.getpid())
        completed_stages = list(prior or [])
        skipped = len(completed_stages)

        for idx, stage in enumerate(pipeline.stages[skipped:], start=skipped + 1):
            stage_sandbox = root_sandbox.attenuate(stage.sandbox)
            skill_obj: Skill | None = None
            if stage.skill:
                skill_obj = self.skill_loader.load(stage.skill)
                if skill_obj is None:
                    err_msg = f"Stage `{stage.id}` failed: skill `{stage.skill}` not found."
                    self.store.update_session(
                        rec.id, status="FAILED", result=err_msg, step_count=idx
                    )
                    failed_root = self.store.get_session(rec.id)
                    assert failed_root is not None
                    return failed_root
                for ct in skill_obj.custom_tools:
                    self._custom_tools.setdefault(ct.name, ct)

            stage_model = (
                stage.model
                or (skill_obj.model if skill_obj and skill_obj.model else None)
                or str(rec.sandbox_config.get("pipeline_model") or rec.model)
            )
            stage_tools = (
                list(stage.tools)
                if stage.tools
                else (list(skill_obj.tools) if skill_obj and skill_obj.tools else list(rec.tools))
            )
            if completed_stages and "agent" not in stage_tools and "all" not in stage_tools:
                stage_tools.append("agent")

            stage_verify: list[str] = []
            for sv in [
                *(skill_obj.verify if skill_obj else []),
                *stage.verify,
                *root_sandbox.verify_commands,
            ]:
                if sv not in stage_verify:
                    stage_verify.append(sv)
            stage_sandbox.verify_commands = stage_verify

            stage_max_steps = stage.max_steps or pipeline.max_steps or self.max_steps
            stage_goal = render_stage_goal(stage, rec.goal, completed_stages, self.store)

            stage_rec = self.store.create_session(
                goal=stage_goal,
                model=stage_model,
                skill=stage.skill,
                tools=stage_tools,
                sandbox_config=stage_sandbox.to_dict(),
                parent_id=rec.id,
                max_steps=stage_max_steps,
            )
            stage_done = await self.execute_session(stage_rec.id)

            digest = self.store.get_session_digest(stage_done.id)
            self.store.add_turn(
                session_id=rec.id,
                step=idx,
                role="tool",
                content=digest,
                tool_cmd=f"stage {stage.id} ({stage_done.id})",
                prompt_tokens=stage_done.total_prompt_tokens,
                completion_tokens=stage_done.total_completion_tokens,
                event_type="completed" if stage_done.status == "COMPLETED" else "tool_error",
            )
            self.store.update_session(
                rec.id,
                step_count=idx,
                peak_tokens=stage_done.peak_tokens,
                add_prompt_tokens=stage_done.total_prompt_tokens,
                add_completion_tokens=stage_done.total_completion_tokens,
            )

            if stage_done.status == "WAITING_INPUT":
                wait_msg = (
                    f"Stage `{stage.id}` ({stage_done.id}) is waiting for input: "
                    f"{stage_done.result or ''}"
                )
                self.store.update_session(
                    rec.id, status="WAITING_INPUT", result=wait_msg, step_count=idx
                )
                waiting_root = self.store.get_session(rec.id)
                assert waiting_root is not None
                return waiting_root

            if stage_done.status != "COMPLETED":
                fail_msg = f"Stage `{stage.id}` ({stage_done.id}) failed: {stage_done.result or ''}"
                self.store.update_session(rec.id, status="FAILED", result=fail_msg, step_count=idx)
                aborted_root = self.store.get_session(rec.id)
                assert aborted_root is not None
                return aborted_root

            completed_stages.append((stage.id, stage_done))

        final_result = completed_stages[-1][1].result or ""
        self.store.update_session(
            rec.id,
            status="COMPLETED",
            result=final_result,
            step_count=len(completed_stages),
        )
        done_root = self.store.get_session(rec.id)
        assert done_root is not None
        return done_root

    async def execute_session(self, session_id: str) -> SessionRecord:
        """Run a session. Worktree sessions are committed whenever they stop."""
        rec = self.store.get_session(session_id)
        if rec is not None and rec.sandbox_config.get("setup_failed"):
            return rec
        out = await self._execute_session_body(session_id)
        if "worktree" not in out.sandbox_config or out.status not in (
            "COMPLETED",
            "FAILED",
            "WAITING_INPUT",
        ):
            return out
        cfg = dict(out.sandbox_config)
        try:
            cfg["commit"] = commit_all(Path(str(cfg["worktree"])), session_id, out.goal)
        except Exception as exc:
            cfg["commit"] = None
            self.store.set_sandbox_config(session_id, cfg)
            note = f"Commit failed: {exc}"
            self.store.update_session(session_id, result=f"{out.result or ''}\n\n{note}".strip())
            return self.store.get_session(session_id) or out
        self.store.set_sandbox_config(session_id, cfg)
        return self.store.get_session(session_id) or out

    async def _execute_session_body(self, session_id: str) -> SessionRecord:
        """Execute the bounded agent loop for a persisted session in SQLite."""
        rec = self.store.get_session(session_id)
        if not rec:
            raise ValueError(f"Session `{session_id}` not found.")

        if isinstance(rec.sandbox_config.get("pipeline"), dict):
            return await self._execute_pipeline_session(rec)

        sandbox = SandboxPolicy.from_dict(rec.sandbox_config)
        skill_obj = self._skill if rec.skill == self.skill_name else None
        if skill_obj is None and rec.skill:
            skill_obj = self.skill_loader.load(rec.skill)
            if skill_obj:
                for ct in skill_obj.custom_tools:
                    self._custom_tools.setdefault(ct.name, ct)

        enabled_tools = list(rec.tools)
        if skill_obj and skill_obj.tools:
            for st in skill_obj.tools:
                if st not in enabled_tools:
                    enabled_tools.append(st)

        verify_commands: list[str] = []
        for sv in [
            *(skill_obj.verify if skill_obj else []),
            *sandbox.verify_commands,
            *(self._verify_commands if rec.parent_id is None else []),
        ]:
            if sv not in verify_commands:
                verify_commands.append(sv)

        try:
            isolation = sandbox.isolation_error()
        except SandboxUnavailableError as exc:
            isolation = str(exc)
        if isolation is not None:
            self.store.add_turn(
                session_id=session_id,
                step=rec.step_count,
                role="tool",
                content=isolation,
                event_type="gate_error",
            )
            self.store.update_session(session_id, status="FAILED", result=isolation)
            refused = self.store.get_session(session_id)
            assert refused is not None
            return refused

        precheck_result = gates_precheck(verify_commands, sandbox)
        if precheck_result is not None:
            self.store.add_turn(
                session_id=session_id,
                step=rec.step_count,
                role="tool",
                content=precheck_result,
                event_type="gate_error",
            )
            self.store.update_session(
                session_id,
                status="FAILED",
                result=f"Verification gate misconfigured: {precheck_result}",
            )
            failed = self.store.get_session(session_id)
            assert failed is not None
            return failed

        output_schema = rec.sandbox_config.get("output_schema") or None

        mux = self.build_multiplexer(
            session_id=session_id,
            enabled_tools=enabled_tools,
            sandbox=sandbox,
            model=rec.model,
        )

        try:
            provider = self._provider or resolve_provider(
                rec.model,
                num_ctx=self.max_context_tokens,
                params=rec.sandbox_config.get("params") or None,
            )
        except Exception as exc:  # e.g. empty api_key_env or bad providers.yaml: fail early
            self.store.add_turn(
                session_id=session_id,
                step=rec.step_count,
                role="tool",
                content=traceback.format_exc()[-4000:],
                event_type="tool_error",
            )
            self.store.update_session(
                session_id, status="FAILED", result=f"Worker error: {type(exc).__name__}: {exc}"
            )
            failed = self.store.get_session(session_id)
            assert failed is not None
            return failed
        assembler = ContextAssembler(
            fold_after_turns=self.fold_observations_after,
            auto_fold=self.auto_fold,
            max_context_tokens=self.max_context_tokens,
            structured=bool(getattr(provider, "structured_history", False)),
            mem_enabled="mem" in mux.tool_names,
            workspace_root=str(sandbox.workspace_root),
        )
        system_prompt = assembler.build_system_prompt(
            toolbox_index=mux.toolbox_index(),
            skill_instructions=skill_obj.instructions if skill_obj else None,
        )

        self.store.update_session(session_id, status="RUNNING", pid=os.getpid())

        step_start = rec.step_count
        step_limit = rec.max_steps
        last_action_sig: tuple[str, str | None] | None = None
        action_history: list[tuple[str, str | None]] = []
        consecutive_verify_failures = 0
        warned_overflow = False

        # Stall guard state: warnings since the last change, reads of one file in a row
        stalls = 0
        pointed: set[str] = set()
        read_file: str | None = None
        read_run = 0
        loop_run = 0

        # Quiet nudge state
        changed = False
        changes: list[str] = []
        green_cmd: str | None = None  # last passing test run, cleared by any later change
        green_nudged = False
        small_hinted: set[str] = set()  # files already pointed to `edit replace`
        empty_streak = 0  # consecutive empty model replies (#135)
        last_run: tuple[int, frozenset[str]] | None = None  # outcome of the last test run
        edited_since_run = False  # a change since the last test run
        traced: set[frozenset[str]] = set()  # failing sets already shown with a runtime trace
        last_test: str | None = None  # last test command, re-run by the harness after each edit
        near_hinted = False  # pointed once to a small edit when only a few tests fail
        asked_tests = False  # asked once to state what the tests expect before the first rewrite
        reasoning_due: str | None = None  # the file whose rewrite waits on that answer
        wrapped_up = False  # one last "finish now" turn before a stall ends the session
        # Restart state: failing check runs per command (counted once per edit in between)
        fail_runs: dict[str, int] = {}
        stale: set[str] = set()
        read_counts: Counter[str] = Counter()
        restarts = 0
        originals: dict[str, bytes] = {}  # existing files as they were before the model wrote them
        # the run that failed fewest tests while passing most, and those files as they were then
        best: tuple[int, frozenset[str], dict[str, bytes]] | None = None
        quiet_run = 0
        steps_hinted = False
        last_reply = ""  # the model's last plain-text answer, never confirmed with `done`

        def reply_note() -> str:
            if not last_reply:
                return ""
            return (
                "\n\nThe model's last reply, never confirmed with `done`:\n"
                + last_reply[:KEPT_REPLY_CHARS]
            )

        def reset_originals(files: dict[str, bytes]) -> list[str]:
            """Put the files the model changed back as in `files`; the names of those reset."""
            reset = []
            for rel, data in files.items():
                path = Path(sandbox.workspace_root) / rel
                with suppress(OSError):
                    if path.read_bytes() != data:
                        path.write_bytes(data)
                        reset.append(rel)
            return reset

        def get_unstuck(step: int, check: str | None, out: str | None) -> SessionRecord | None:
            """Stuck, however it showed (the same check failing after edits, or stalls the
            wrap-up did not end): restart from a described state, and once restarts are used
            up hand the task back to the caller (WAITING_INPUT) instead of burning steps."""
            nonlocal restarts, last_action_sig, read_file, read_run, loop_run, stalls
            handback = restarts if restarts >= MAX_RESTARTS else 0
            tried = describe_attempts(
                list(modified_files(sandbox.workspace_root, rec.created_at)),
                changes,
                read_counts,
                check,
                fail_runs.get(check or "", 0),
            )
            # #173: the same check kept failing: set the attempt aside and start fresh from the
            # files as they were (Olausson et al., ICLR 2024: for weaker models a new sample beats
            # repairing a wrong one). Files the model created are left as they are. (A near pass
            # never gets here: it goes back to its best version in place.)
            fresh = sorted(reset_originals(originals)) if check and not handback else []
            text = restart_message(
                step=step,
                check_cmd=check,
                failing_output=out,
                files=modified_files(sandbox.workspace_root, rec.created_at),
                tried=tried,
                handback=handback,
                fresh=fresh,
                failing=sorted(last_run[1])[:5] if last_run else None,
            )
            if handback:
                text += reply_note()
                self.store.add_turn(
                    session_id=session_id, step=step, role="tool", content=f"[WAITING_INPUT] {text}"
                )
                self.store.update_session(
                    session_id, status="WAITING_INPUT", result=text, step_count=step
                )
                return self.store.get_session(session_id)
            self.store.add_turn(
                session_id=session_id, step=step, role="user", content=text, event_type="restart"
            )
            restarts += 1
            fail_runs.clear()
            stale.clear()
            read_counts.clear()
            action_history.clear()
            last_action_sig = None
            read_file, read_run, loop_run, stalls = None, 0, 0, 0
            return None

        try:
            for step in range(step_start + 1, step_limit + 1):
                # 1. Poll SQLite inbox before each reasoning step
                inbox_msgs = self.store.consume_inbox(session_id)
                if inbox_msgs:
                    last_action_sig = None
                    action_history.clear()
                for imsg in inbox_msgs:
                    self.store.add_turn(
                        session_id=session_id,
                        step=step,
                        role="user",
                        content=f"[Follow-up instruction]: {imsg}",
                    )

                # 1b. Token budget: pause before the next model call once the budget is spent.
                # The call that crossed the budget has already run and been recorded.
                fresh = self.store.get_session(session_id)
                assert fresh is not None
                used = _tokens_used(fresh)
                if fresh.max_tokens and used >= fresh.max_tokens:
                    text = _token_budget_text(used, fresh.max_tokens, step - 1) + reply_note()
                    self.store.add_turn(
                        session_id=session_id,
                        step=step,
                        role="tool",
                        content=f"[WAITING_INPUT] {text}",
                    )
                    self.store.update_session(
                        session_id, status="WAITING_INPUT", result=text, step_count=step - 1
                    )
                    paused = self.store.get_session(session_id)
                    assert paused is not None
                    return paused

                # 2. Assemble context with ephemeral observation folding
                turns = after_restart(self.store.get_turns(session_id))
                observations = self.store.list_observations(session_id)
                pins = self.store.get_pins(session_id)
                messages = assembler.assemble(
                    system_prompt=system_prompt,
                    goal=rec.goal,
                    turns=turns,
                    observations=observations,
                    pins=pins,
                    current_step=step,
                )

                est_tokens = estimate_messages_tokens(messages, [ACT_TOOL_SCHEMA])
                if assembler.overflow and not warned_overflow:
                    warned_overflow = True
                    print(
                        f"tether: warning: context is ~{assembler.overflow} tokens over "
                        f"--context-tokens {self.max_context_tokens} (goal, system prompt and "
                        "the latest step alone do not fit); raise the budget.",
                        file=sys.stderr,
                    )
                t_llm_start = time.perf_counter()
                for outage in range(OUTAGE_RETRIES + 1):
                    try:
                        resp = await provider.generate(messages, [ACT_TOOL_SCHEMA])
                        break
                    except ProviderError:
                        if outage == OUTAGE_RETRIES:
                            raise
                        await asyncio.sleep(
                            float(os.environ.get("TETHER_OUTAGE_BACKOFF", "10")) * 2**outage
                        )
                llm_duration_ms = int((time.perf_counter() - t_llm_start) * 1000)

                assembler.calibrate(est_tokens, resp.prompt_tokens)
                prompt_tokens = resp.prompt_tokens if resp.prompt_tokens > 0 else est_tokens
                completion_tokens = resp.completion_tokens
                actual_tokens = max(est_tokens, prompt_tokens + completion_tokens)
                resolved_model = (
                    f"ollama/{provider.model_name}"
                    if rec.model.startswith("ollama/")
                    and not rec.model.endswith(provider.model_name)
                    else None
                )
                self.store.update_session(
                    session_id,
                    model=resolved_model,
                    step_count=step,
                    peak_tokens=actual_tokens,
                    add_prompt_tokens=prompt_tokens,
                    add_completion_tokens=completion_tokens,
                )
                # 3. If the model emitted plain text without calling `act`, nudge it (Rule 3)
                if (
                    resp.action is None
                    and reasoning_due
                    and (resp.content or "").strip()
                    and not resp.empty
                ):
                    # #173: the plain-words answer to [BEFORE WRITING] is the expected reply
                    self.store.add_turn(
                        session_id=session_id,
                        step=step,
                        role="assistant",
                        content=resp.content,
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        duration_ms=llm_duration_ms,
                    )
                    self.store.add_turn(
                        session_id=session_id,
                        step=step,
                        role="user",
                        content=f"Now write `{reasoning_due}` so it gives exactly those results.",
                    )
                    empty_streak = 0
                    reasoning_due = None
                    continue
                if resp.action is None:
                    prose = (resp.content or "").strip()
                    if len(prose) >= PROSE_ANSWER_CHARS:
                        last_reply = prose
                    empty_streak = empty_streak + 1 if resp.empty else 0
                    if empty_streak >= 3:
                        self.store.add_turn(
                            session_id=session_id,
                            step=step,
                            role="assistant",
                            content=resp.content,
                            prompt_tokens=prompt_tokens,
                            completion_tokens=completion_tokens,
                            duration_ms=llm_duration_ms,
                        )
                        stop_text = (
                            f"stopped: 3 empty replies in a row from {provider.model_name}. "
                            "Try --param think=false or another model."
                        )
                        self.store.update_session(
                            session_id, status="WAITING_INPUT", result=stop_text, step_count=step
                        )
                        done_rec = self.store.get_session(session_id)
                        assert done_rec is not None
                        return done_rec
                    self.store.add_turn(
                        session_id=session_id,
                        step=step,
                        role="assistant",
                        content=resp.content or "(no output)",
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        duration_ms=llm_duration_ms,
                        event_type="nudge",
                    )
                    self.store.add_turn(
                        session_id=session_id,
                        step=step,
                        role="user",
                        content=resp.hint
                        or (
                            "System reminder: your reply above was not delivered; only `done` "
                            'delivers. If it is your answer, call `act("done", stdin="<your '
                            'answer>")`; otherwise run your next command with `act(cmd, stdin)`.'
                            if len(prose) >= PROSE_ANSWER_CHARS
                            else "System reminder: Use `act(cmd, stdin)` to execute a tool "
                            'command, or call `act("done", stdin="<final deliverable>")` to finish.'
                        ),
                    )
                    continue

                empty_streak = 0
                reasoning_due = None
                cmd = normalize_cmd(resp.action.cmd)
                stdin = resp.action.stdin
                action_sig = (cmd.strip(), stdin)
                is_loop_stall = action_sig == last_action_sig and not cmd.strip().startswith("done")
                cycle = (
                    None
                    if is_loop_stall or cmd.strip().startswith("done")
                    else detect_cycle([*action_history, action_sig])
                )

                target = read_target(cmd) if not (is_loop_stall or cycle) else None
                if target is None or target != read_file:
                    read_file, read_run = target, 0
                read_run += 1 if target else 0
                read_counts.update([target] if target else [])
                range_stall = bool(target) and read_run >= RANGE_STALL_READS

                assistant_turn_id = self.store.add_turn(
                    session_id=session_id,
                    step=step,
                    role="assistant",
                    content=resp.content,
                    thinking=resp.thinking,
                    tool_cmd=cmd,
                    tool_stdin=stdin,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    duration_ms=llm_duration_ms,
                    event_type=(
                        "loop_stall"
                        if is_loop_stall
                        else "cycle_stall"
                        if cycle or range_stall
                        else "ok"
                    ),
                )

                if is_loop_stall or cycle or range_stall:
                    stalls += 1
                    if stalls >= STALL_ABORT:
                        # A model that fixed the task and then only repeats its check has
                        # finished: if every verify gate passes after a change, say so (#163)
                        finished = await self._finished_by_harness(
                            sandbox, verify_commands, green_cmd, changed
                        )
                        if not finished and not wrapped_up:
                            # Work that keeps re-reading (a review, a plan, a file it already
                            # wrote) gets one more turn to deliver instead of ending empty
                            wrapped_up, stalls = True, STALL_ABORT - 1
                            self.store.add_turn(
                                session_id=session_id,
                                step=step,
                                role="tool",
                                content=(
                                    "[WRAP UP] You keep repeating a command. If the task is "
                                    'complete, call `act("done", stdin="<what is done and what '
                                    'is left>")`.'
                                    if changed
                                    else "[WRAP UP] You keep re-reading. Stop and answer now from "
                                    "what you have read: write the file the task asked for, if "
                                    'any, then call `act("done", stdin="<your final answer>")`.'
                                ),
                            )
                            continue
                        if finished:
                            self.store.update_session(
                                session_id, status="COMPLETED", result=finished
                            )
                            done_rec = self.store.get_session(session_id)
                            assert done_rec is not None
                            return done_rec
                        if (handed := get_unstuck(step, None, None)) is not None:
                            return handed
                        continue
                if range_stall:
                    read_run = max(0, RANGE_STALL_READS - 2)  # repeat offenders: warn every 2nd
                    self.store.add_turn(
                        session_id=session_id,
                        step=step,
                        role="tool",
                        content=(
                            f"[CYCLE DETECTED] {RANGE_STALL_READS} reads of `{target}` in a row "
                            "without editing. Stop exploring: make your edit now (a whole-file "
                            '`edit write` is fine), or call `act("done", stdin="...")`.'
                        ),
                    )
                    continue
                if is_loop_stall:
                    loop_run += 1
                    if loop_run == 1:
                        stall_msg = (
                            f"[LOOP DETECTED] You just ran `{cmd.strip()}` with identical input "
                            "in the previous step. Do not repeat it: use the output above, then "
                            "do what the task asked (write or edit the file) or call "
                            '`act("done", stdin="...")` to finish.'
                        )
                    else:
                        stall_msg = (
                            "[LOOP DETECTED] You already have this output above. Use it now: "
                            "write the file the task asked for or make the next edit, then call "
                            f'`act("done", stdin="...")`. Repeating `{cmd.strip()}` changes '
                            "nothing."
                        )
                    self.store.add_turn(
                        session_id=session_id,
                        step=step,
                        role="tool",
                        content=stall_msg,
                    )
                    continue
                if cycle:
                    action_history.clear()
                    cycle_msg = (
                        f"[CYCLE DETECTED] You are repeating the commands "
                        f"{' -> '.join(f'`{c}`' for c in cycle)} "
                        "and the output/file may not have changed. Stop: re-read the last output, "
                        "change your approach (for example a different pattern or a whole-file "
                        'edit), or call `act("done", stdin="...")`.'
                    )
                    self.store.add_turn(
                        session_id=session_id,
                        step=step,
                        role="tool",
                        content=cycle_msg,
                    )
                    continue
                last_action_sig = action_sig
                loop_run = 0
                action_history.append(action_sig)

                # #199: a repeated read of an unchanged live file is answered with a pointer, once
                live_obs = live_read_obs(cmd, turns, observations, str(sandbox.workspace_root))
                if live_obs and live_obs not in pointed:
                    pointed.add(live_obs)
                    self.store.add_turn(
                        session_id=session_id,
                        step=step,
                        role="tool",
                        content=(
                            f"[{live_obs} unchanged] `{cmd.strip()}` was already read and the "
                            "file has not changed since; its output is above. Use it."
                        ),
                    )
                    continue

                rewrites = [os.path.normpath(p) for p in whole_file_targets(cmd)]

                # #173: before the first rewrite of a starting file, state what its tests expect
                # (AlphaCodium, Ridnik et al. 2024: test reasoning before code); asked once
                root = Path(sandbox.workspace_root)
                suite = (
                    None
                    if asked_tests or not rewrites
                    else suite_for(rewrites[0], root, rec.created_at)
                )
                if suite:
                    asked_tests, reasoning_due = True, rewrites[0]
                    last_action_sig = None  # sending the same write again is not a loop
                    action_history.pop()
                    self.store.update_turn_telemetry(assistant_turn_id, event_type="nudge")
                    self.store.add_turn(
                        session_id=session_id,
                        step=step,
                        role="tool",
                        content=(
                            f"[BEFORE WRITING] `{reasoning_due}` was not written yet. First reply "
                            f"in plain words, with no command: for the 3 tests in `{suite}` that "
                            "look hardest, what each one calls, the exact result it expects, and "
                            f"how your design gives it. Then write `{reasoning_due}`."
                        ),
                    )
                    continue

                quiet = is_quiet(cmd)
                before = {} if quiet else snapshot(cmd, Path(sandbox.workspace_root))
                for rel, data in before.items():  # untouched since the session started
                    with suppress(OSError):
                        path = Path(sandbox.workspace_root) / rel
                        if path.stat().st_mtime < rec.created_at:
                            key = snapshot_key(rel, Path(sandbox.workspace_root))
                            if key not in originals:
                                originals[key] = data
                                self.store.record_snapshot(session_id, key, data)
                # a file the command creates has no bytes yet: its snapshot is NULL
                for rel in missing_targets(cmd, Path(sandbox.workspace_root)):
                    self.store.record_snapshot(
                        session_id, snapshot_key(rel, Path(sandbox.workspace_root)), None
                    )
                # named arguments (sed -i f, mv new f) are kept for `tether diff` only
                arg_bytes = (
                    {} if quiet else arg_snapshot(cmd, Path(sandbox.workspace_root), skip=before)
                )
                for rel, data in arg_bytes.items():  # not added to `originals`
                    with suppress(OSError):
                        if (Path(sandbox.workspace_root) / rel).stat().st_mtime < rec.created_at:
                            key = snapshot_key(rel, Path(sandbox.workspace_root))
                            self.store.record_snapshot(session_id, key, data)
                t_tool_start = time.perf_counter()
                dispatch = await mux.execute(cmd, stdin=stdin)
                tool_duration_ms = int((time.perf_counter() - t_tool_start) * 1000)

                if dispatch.is_waiting_input:
                    late_inbox = self.store.consume_inbox(session_id)
                    if late_inbox:
                        for lmsg in late_inbox:
                            self.store.add_turn(
                                session_id=session_id,
                                step=step,
                                role="user",
                                content=f"[Follow-up instruction]: {lmsg}",
                            )
                        continue

                    question_text = dispatch.final_result or ""
                    self.store.add_turn(
                        session_id=session_id,
                        step=step,
                        role="tool",
                        content=f"[WAITING_INPUT] {question_text}",
                        duration_ms=tool_duration_ms,
                    )
                    self.store.update_session(
                        session_id,
                        status="WAITING_INPUT",
                        result=question_text,
                        step_count=step,
                    )
                    waiting_rec = self.store.get_session(session_id)
                    assert waiting_rec is not None
                    return waiting_rec

                if dispatch.is_done:
                    # Check if any new message arrived in inbox while executing this step
                    late_inbox = self.store.consume_inbox(session_id)
                    if late_inbox:
                        for lmsg in late_inbox:
                            self.store.add_turn(
                                session_id=session_id,
                                step=step,
                                role="user",
                                content=f"[Follow-up instruction]: {lmsg}",
                            )
                        continue

                    # 4. Run deterministic pre-`done` verification gates if configured
                    schema_err = (
                        validate_output(dispatch.final_result or "", output_schema)
                        if output_schema
                        else None
                    )
                    if schema_err or verify_commands:
                        t_gate_start = time.perf_counter()
                        gate_failure = (
                            ("output-schema", 1, schema_err, False)
                            if schema_err
                            else await self._run_verification_gates(sandbox, verify_commands)
                        )
                        gate_duration_ms = int((time.perf_counter() - t_gate_start) * 1000)
                        if gate_failure is not None:
                            failed_cmd, exit_code, gate_out, gate_broken = gate_failure
                            if gate_broken:
                                # Environment problem the model cannot fix: fail fast, no retries.
                                self.store.update_turn_telemetry(
                                    assistant_turn_id, event_type="gate_error"
                                )
                                self.store.add_turn(
                                    session_id=session_id,
                                    step=step,
                                    role="tool",
                                    content=(
                                        f"[VERIFICATION GATE BROKEN: `{failed_cmd}` "
                                        f"(exit {exit_code})] {gate_out}\n"
                                        "The gate itself is misconfigured, not your work."
                                    ),
                                    duration_ms=tool_duration_ms + gate_duration_ms,
                                )
                                self.store.update_session(
                                    session_id,
                                    status="FAILED",
                                    result=(
                                        f"Verification gate `{failed_cmd}` misconfigured: "
                                        f"{gate_out}"
                                    ),
                                    step_count=step,
                                )
                                broken_rec = self.store.get_session(session_id)
                                assert broken_rec is not None
                                return broken_rec
                            consecutive_verify_failures += 1
                            self.store.update_turn_telemetry(
                                assistant_turn_id, event_type="gate_fail"
                            )
                            gate_msg = (
                                f"[VERIFICATION GATE FAILED: `{failed_cmd}` (exit {exit_code})]\n"
                                f"{gate_out}\n"
                                "Fix the reported issues before calling `done` again."
                            )
                            obs = self.store.add_observation(
                                session_id=session_id,
                                step=step,
                                cmd=f"verify: {failed_cmd}",
                                raw_output=gate_msg,
                            )
                            self.store.add_turn(
                                session_id=session_id,
                                step=step,
                                role="tool",
                                content=gate_msg,
                                obs_id=obs.id,
                                duration_ms=tool_duration_ms + gate_duration_ms,
                            )
                            if (
                                self.max_verify_failures > 0
                                and consecutive_verify_failures >= self.max_verify_failures
                            ):
                                self.store.update_session(
                                    session_id,
                                    status="FAILED",
                                    result=(
                                        f"Verification gate `{failed_cmd}` failed "
                                        f"{consecutive_verify_failures} consecutive times."
                                    ),
                                    step_count=step,
                                )
                                failed_rec = self.store.get_session(session_id)
                                assert failed_rec is not None
                                return failed_rec
                            continue

                    self.store.update_turn_telemetry(assistant_turn_id, event_type="completed")
                    final_text = dispatch.final_result or ""
                    self.store.add_turn(
                        session_id=session_id,
                        step=step,
                        role="tool",
                        content=f"[COMPLETED] {final_text}",
                        duration_ms=tool_duration_ms,
                    )
                    self.store.update_session(
                        session_id,
                        status="COMPLETED",
                        result=final_text,
                        step_count=step,
                    )
                    done_rec = self.store.get_session(session_id)
                    assert done_rec is not None
                    return done_rec

                if dispatch.error_kind in ("syntax_error", "unknown_cmd"):
                    self.store.update_turn_telemetry(assistant_turn_id, event_type="syntax_error")
                elif dispatch.error_kind == "sandbox_violation":
                    self.store.update_turn_telemetry(
                        assistant_turn_id,
                        event_type="sandbox_violation",
                        rule=sandbox_rule(dispatch.output),
                    )
                elif dispatch.is_error:
                    self.store.update_turn_telemetry(assistant_turn_id, event_type="tool_error")

                # Quiet nudge: track consecutive read-only/verification steps after a change
                if is_quiet(cmd):
                    quiet_run += 1
                else:
                    changed = True
                    changes.append(cmd)
                    quiet_run = 0
                    stalls = 0
                    green_cmd = None
                    green_nudged = False
                    stale.update(fail_runs)
                    edited_since_run = True

                out = dispatch.output
                tcmd, tout = cmd, dispatch.output  # the test run this step, if any
                if _TEST_CMD.search(cmd) and is_quiet(cmd):
                    last_test = cmd.strip()
                elif last_test and before and not dispatch.is_error:
                    # #173 (Aider's auto-test): run the tests after each edit, so a weak model
                    # never types a second version blind (each rewrite costs it 30-100 s)
                    tcmd, tout = last_test, (await mux.execute(last_test)).output
                    out += f"\n[auto-test] `{last_test}` after your edit:\n{tout}"
                if (
                    _TEST_CMD.search(tcmd)
                    and _TESTS_RED.search(tout)
                    and not tests_green(tcmd, tout)
                ):
                    out += failing_test_source(tout, Path(sandbox.workspace_root))
                elif (
                    is_quiet(cmd)
                    and not asked_tests
                    and not _TEST_CMD.search(cmd)
                    and (pair := suite_read(cmd, Path(sandbox.workspace_root), rec.created_at))
                ):
                    # #173: test reasoning (AlphaCodium) asked with the test file, so no
                    # typed version is held back for it
                    asked_tests, reasoning_due = True, pair[0]
                    out += (
                        f"\n[BEFORE WRITING] Before you write `{pair[0]}`, reply in plain words, "
                        f"with no command: for the 3 tests in `{pair[1]}` that look hardest, what "
                        "each one calls, the exact result it expects, and how your design gives "
                        f"it. Then write `{pair[0]}`."
                    )
                if _TEST_CMD.search(tcmd) and (outcome := run_outcome(tout)):
                    if last_run:
                        out += regression_note(last_run, outcome)
                    # #173: after a change the same tests fail again, or only a few still fail:
                    # show what the code did at runtime
                    same = last_run is not None and outcome[1] and outcome[1] == last_run[1]
                    n_failed = failing_count(tout, outcome[1])
                    near = 0 < n_failed <= NEAR_PASS
                    test_id = failing_test_id(tout)
                    if (same or near) and edited_since_run and outcome[1] not in traced and test_id:
                        traced.add(outcome[1])
                        root = Path(sandbox.workspace_root)
                        smallest = smallest_failing(test_id, outcome[1], root)
                        out += await runtime_trace(sandbox, smallest)
                    if near and outcome[0] > 2 * n_failed and not near_hinted:
                        # #173: paasio at 22/25 spent its last 100 s on 103-line rewrites
                        near_hinted = True
                        target = f"`edit replace {min(originals)}`" if originals else "a small edit"
                        out += (
                            f"\n[NUDGE] {n_failed} of {outcome[0]} tests still fail. Fix the code "
                            f"they call with {target}; a whole-file rewrite is slow and can break "
                            "what passes."
                        )
                    last_run = outcome
                    edited_since_run = False
                    if outcome[0] > 2 * n_failed and (best is None or n_failed < best[0]):
                        root = Path(sandbox.workspace_root)
                        files = {
                            rel: (root / rel).read_bytes()
                            for rel in originals
                            if (root / rel).is_file()
                        }
                        best = (n_failed, outcome[1], files)
                if before and not dispatch.is_error:
                    root = Path(sandbox.workspace_root)
                    out += unchanged_note(before, root) or small_change_note(
                        cmd, before, root, small_hinted
                    )
                if changed and not dispatch.is_error and tests_green(tcmd, tout):
                    green_cmd = tcmd
                    if not green_nudged:
                        out += (
                            "\n[NUDGE] Tests pass after your last change. If the task is complete "
                            'call `act("done", stdin="...")` now.'
                        )
                        green_nudged = True
                # Nudge after QUIET_NUDGE_STEPS quiet steps following a change, then every
                # QUIET_NUDGE_EVERY more while the model keeps only reading or verifying
                if (
                    changed
                    and quiet_run >= QUIET_NUDGE_STEPS
                    and (quiet_run - QUIET_NUDGE_STEPS) % QUIET_NUDGE_EVERY == 0
                ):
                    out += (
                        f"\n[NUDGE] No file changes for {quiet_run} steps. If the task is "
                        "complete call `done`; otherwise make your next edit."
                    )
                elif (
                    not changed
                    and quiet_run >= EXPLORE_NUDGE_STEPS
                    and (quiet_run - EXPLORE_NUDGE_STEPS) % EXPLORE_NUDGE_EVERY == 0
                ):
                    out += (
                        f"\n[NUDGE] No file changes in {quiet_run} steps. Make your edit now, or "
                        "call `done` with what you found."
                    )

                if not steps_hinted and step_limit >= STEPS_LEFT_MIN and step >= step_limit * 0.75:
                    out += (
                        f"\n[NUDGE] {step_limit - step} steps left. Finish the current edit, then "
                        "call `done` with what is done and what is left."
                    )
                    steps_hinted = True

                # The same check failed again after another edit (counted once per edit between)
                check = tcmd.strip()
                red = bool(
                    _TEST_CMD.search(tcmd)
                    and _TESTS_RED.search(tout)
                    and not tests_green(tcmd, tout)
                )
                if red and (check not in fail_runs or check in stale):
                    fail_runs[check] = fail_runs.get(check, 0) + 1
                    stale.discard(check)
                if (
                    red
                    and fail_runs[check] >= RESTART_AFTER_FAILS
                    and best
                    and best[0] <= NEAR_PASS
                ):
                    # #173: near a pass a restart wiped the history and paasio spent its last
                    # ~100 s re-reading the tests; go back to the best version in place instead
                    fail_runs.clear()
                    stale.clear()
                    if reset_originals(best[2]):
                        out += (
                            f"\n[RESTORED] Your last {RESTART_AFTER_FAILS} changes did not beat "
                            "your best version, so its files are back. It failed only: "
                            f"{', '.join(sorted(best[1])[:5])}. Fix those from there."
                        )

                # Record tool observation in SQLite (auto-chunks into FTS5)
                obs = self.store.add_observation(
                    session_id=session_id,
                    step=step,
                    cmd=cmd,
                    raw_output=out,
                )
                self.store.add_turn(
                    session_id=session_id,
                    step=step,
                    role="tool",
                    content=out,
                    obs_id=obs.id,
                    duration_ms=tool_duration_ms,
                )

                # Restart: continue from a fresh history that describes the state instead of
                # replaying the failed attempts.
                if red and fail_runs.get(check, 0) >= RESTART_AFTER_FAILS:
                    if (handed := get_unstuck(step, check, tout)) is not None:
                        return handed

            # Max steps reached without explicit `done`
            finished = await self._finished_by_harness(sandbox, verify_commands, green_cmd, changed)
            if finished:
                self.store.update_session(session_id, status="COMPLETED", result=finished)
            else:
                # Out of steps without `done` is stuck too: hand back what is known (`send`
                # extends the budget) instead of failing
                text = await self._unfinished_result(
                    f"[STUCK: out of steps ({rec.max_steps}) without calling `done`.]",
                    sandbox,
                    verify_commands,
                    changes,
                )
                text += reply_note()
                self.store.add_turn(
                    session_id=session_id,
                    step=step_limit,
                    role="tool",
                    content=f"[WAITING_INPUT] {text}",
                )
                self.store.update_session(
                    session_id,
                    status="WAITING_INPUT",
                    result=f"{text}\nRefine the request or give guidance, then send it again.",
                )
        except Exception as exc:
            cur = self.store.get_session(session_id)
            self.store.add_turn(
                session_id=session_id,
                step=cur.step_count if cur else 0,
                role="tool",
                content=traceback.format_exc()[-4000:],
                event_type="tool_error",
            )
            detail = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
            self.store.update_session(
                session_id,
                status="FAILED",
                result=f"Worker error: {detail}",
            )

        final_rec = self.store.get_session(session_id)
        assert final_rec is not None
        return final_rec
