"""Headless CLI (`tether run|pipeline|status|read|query|send|wait|stop|list|stats`)."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import os
import signal
import sys
from pathlib import Path

import yaml

from tether import __version__, api
from tether.diff import render_diff
from tether.harness import Harness, PipelineResumeError
from tether.progress import watch
from tether.providers.base import parse_params
from tether.sandbox import (
    SandboxPolicy,
    SandboxUnavailableError,
    parse_allow_outside,
    parse_limits,
    parse_web_allow,
)
from tether.store import SessionRecord, SQLiteStore
from tether.worktree import WorktreeError

EXIT_USAGE = api.EXIT_USAGE

_KNOWN_SUBCOMMANDS = {
    "run",
    "pipeline",
    "status",
    "read",
    "query",
    "send",
    "allow",
    "wait",
    "stop",
    "list",
    "stats",
    "retro",
    "events",
    "diff",
    "misses",
    "mcp",
    "export",
    "doctor",
    "replay",
    "_worker",
}


def _add_json(p: argparse.ArgumentParser) -> None:
    p.add_argument("--json", action="store_true", help="Machine-readable JSON output")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tether",
        description="Tether: Headless-first LLM-Native Micro-Harness",
    )
    parser.add_argument("--version", action="version", version=f"tether {__version__}")
    sub = parser.add_subparsers(dest="subcommand")

    # `tether run`
    p_run = sub.add_parser("run", help="Run a task inline or as a detached headless session")
    p_run.add_argument(
        "--headless", action="store_true", help="Run detached in background and print session ID"
    )
    p_run.add_argument(
        "--model", type=str, default=None, help="Model (e.g. ollama/qwen3.5:9b, openai/gpt-4o-mini)"
    )
    p_run.add_argument(
        "--skill", type=str, default=None, help="Skill name from ./skills/ or ~/.tether/skills/"
    )
    p_run.add_argument(
        "--tools", type=str, default=None, help="Comma-separated tools (e.g. web,mem,bash or all)"
    )
    p_run.add_argument(
        "--verify",
        action="append",
        default=None,
        help="Deterministic verification gate command to run before `done` (repeatable)",
    )
    p_run.add_argument(
        "--sandbox",
        type=str,
        default="workspace-write",
        choices=["workspace-write", "read-only"],
        help="Deterministic sandbox profile",
    )
    p_run.add_argument(
        "--no-network",
        action="store_true",
        help="Disable network inside the bash sandbox (requires bwrap; fails closed without it)",
    )
    p_run.add_argument(
        "--web-allow",
        type=str,
        default=None,
        help="Comma list of domains the web tool may reach, e.g. python.org,*.github.com",
    )
    p_run.add_argument(
        "--allow",
        action="append",
        metavar="PREFIX",
        help="command prefix that runs outside the jail (repeatable)",
    )
    p_run.add_argument(
        "--limit",
        action="append",
        default=None,
        metavar="K=V",
        help="Resource limit, repeatable: cpu=SECONDS mem=MB procs=N fsize=MB; opt-in",
    )
    p_run.add_argument(
        "--allow-unsandboxed",
        action="store_true",
        help="Run write sessions without bwrap (command checks only)",
    )
    p_run.add_argument("--max-steps", type=int, default=15, help="Max reasoning steps")
    p_run.add_argument(
        "--max-tokens",
        type=int,
        default=None,
        help="Token budget (prompt + completion); pauses as WAITING_INPUT when reached",
    )
    p_run.add_argument(
        "--context-tokens", type=int, default=None, help="Context token budget (default 32768)"
    )
    p_run.add_argument(
        "--fold-after",
        type=int,
        default=None,
        help="Fold older than N turns (default auto: K=2, up to 8 by re-reads; N = fixed rule)",
    )
    p_run.add_argument(
        "--db", type=str, default=None, help="SQLite DB path (default .tether/tether.db)"
    )
    p_run.add_argument(
        "--param",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Model request parameter, repeatable (e.g. --param temperature=0 --param think=false)",
    )
    p_run.add_argument(
        "--output-schema",
        type=str,
        default=None,
        help="JSON Schema file; the `done` deliverable must validate or `done` is rejected",
    )
    p_run.add_argument(
        "--result-file", type=str, default=None, help="Write the deliverable here, not to stdout"
    )
    p_run.add_argument(
        "-v", "--verbose", action="store_true", help="Print one line per step to stderr"
    )
    p_run.add_argument(
        "--worktree", action="store_true", help="Run in a git worktree on tether/<id>"
    )
    p_run.add_argument("--worktree-from", help="Base ref for --worktree (default HEAD)")
    p_run.add_argument("--setup", help="Shell command run in the worktree before the model starts")
    _add_json(p_run)
    p_run.add_argument("goal", nargs="+", help="Task goal or instruction")

    # `tether pipeline`
    p_pipe = sub.add_parser(
        "pipeline",
        help="Execute a declarative multi-stage YAML workflow inline or headless",
    )
    p_pipe.add_argument(
        "pipeline_file",
        nargs="?",
        help="Path to declarative pipeline YAML manifest (omit with --resume)",
    )
    p_pipe.add_argument(
        "--resume",
        metavar="SESSION_ID",
        default=None,
        help="Resume a failed or waiting pipeline from its first unfinished stage; --model, "
        "--sandbox, --no-network, --max-steps, --context-tokens and --fold-after are ignored "
        "(the stored root sandbox and model are used)",
    )
    p_pipe.add_argument(
        "--headless", action="store_true", help="Run detached in background and print session ID"
    )
    p_pipe.add_argument(
        "--model",
        type=str,
        default=None,
        help="Default fallback model when a stage omits `model`",
    )
    p_pipe.add_argument(
        "--sandbox",
        type=str,
        default="workspace-write",
        choices=["workspace-write", "read-only"],
        help="Root deterministic sandbox profile (stages can only narrow)",
    )
    p_pipe.add_argument(
        "--no-network",
        action="store_true",
        help="Disable network inside the bash sandbox (requires bwrap; fails closed without it)",
    )
    p_pipe.add_argument(
        "--web-allow",
        type=str,
        default=None,
        help="Comma list of domains the web tool may reach (stages can only narrow)",
    )
    p_pipe.add_argument(
        "--allow",
        action="append",
        metavar="PREFIX",
        help="command prefix that runs outside the jail (repeatable)",
    )
    p_pipe.add_argument(
        "--limit",
        action="append",
        default=None,
        metavar="K=V",
        help="Resource limit, repeatable: cpu=SECONDS mem=MB procs=N fsize=MB; opt-in",
    )
    p_pipe.add_argument(
        "--allow-unsandboxed",
        action="store_true",
        help="Run write sessions without bwrap (command checks only)",
    )
    p_pipe.add_argument(
        "--max-steps", type=int, default=15, help="Default max reasoning steps per stage"
    )
    p_pipe.add_argument(
        "--db", type=str, default=None, help="SQLite DB path (default .tether/tether.db)"
    )
    p_pipe.add_argument(
        "--context-tokens", type=int, default=None, help="Context token budget (default 32768)"
    )
    p_pipe.add_argument(
        "--fold-after",
        type=int,
        default=None,
        help="Fold older than N turns (default auto: K=2, up to 8 by re-reads; N = fixed rule)",
    )
    p_pipe.add_argument(
        "--result-file", type=str, default=None, help="Write the deliverable here, not to stdout"
    )
    _add_json(p_pipe)
    p_pipe.add_argument("goal", nargs="*", help="Root task goal or instruction")

    # `tether status`
    p_status = sub.add_parser("status", help="Show live session status and token metrics")
    p_status.add_argument("session_id", help="Session ID (e.g. ses_...)")
    p_status.add_argument("--db", type=str, default=None)
    _add_json(p_status)

    # `tether read`
    p_read = sub.add_parser(
        "read",
        help="Read session final result (default/--full), digest (--digest) or step log (--steps)",
    )
    p_read.add_argument("session_id", help="Session ID")
    read_mode = p_read.add_mutually_exclusive_group()
    read_mode.add_argument(
        "--digest", action="store_true", help="Show compact ~50-token digest card"
    )
    read_mode.add_argument("--steps", action="store_true", help="Show step-by-step work log")
    read_mode.add_argument(
        "--thinking", action="store_true", help="Show the stored model thinking per step"
    )
    read_mode.add_argument(
        "--full", action="store_true", help="Show the full final result (the default)"
    )
    p_read.add_argument("--db", type=str, default=None)
    _add_json(p_read)

    # `tether query`
    p_query = sub.add_parser(
        "query", help="BM25 FTS5 RAG query over session deliverables & observations"
    )
    p_query.add_argument("session_id", help="Session ID")
    p_query.add_argument("query", nargs="+", help="Search keywords")
    p_query.add_argument("--top", type=int, default=3, help="Top K chunks to return")
    p_query.add_argument("--db", type=str, default=None)

    # `tether send`
    p_send = sub.add_parser(
        "send", help="Send a follow-up message to a running or completed session"
    )
    p_send.add_argument("session_id", help="Session ID")
    p_send.add_argument("--headless", action="store_true", help="Resume in background if completed")
    p_send.add_argument("--db", type=str, default=None)
    _add_json(p_send)
    p_send.add_argument("message", nargs="+", help="Follow-up instruction")

    # `tether allow`: the same as `tether send <id> approve` (#59)
    p_allow = sub.add_parser("allow", help="Approve a session's pending [APPROVAL NEEDED] command")
    p_allow.add_argument("session_id", help="Session ID")
    p_allow.add_argument("--headless", action="store_true", help="Resume in the background")
    p_allow.add_argument("--db", type=str, default=None)
    _add_json(p_allow)

    # `tether wait`
    p_wait = sub.add_parser("wait", help="Wait for one or more headless sessions to finish")
    p_wait.add_argument("session_ids", nargs="+", help="Session ID(s)")
    p_wait.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        help="seconds to wait before giving up (default: 120 seconds)",
    )
    p_wait.add_argument("--db", type=str, default=None)
    _add_json(p_wait)

    # `tether stop`
    p_stop = sub.add_parser("stop", help="Terminate a running detached session")
    p_stop.add_argument("session_id", help="Session ID")
    p_stop.add_argument("--db", type=str, default=None)
    _add_json(p_stop)

    # `tether list`
    p_list = sub.add_parser("list", help="List recent sessions")
    p_list.add_argument("--limit", type=int, default=20)
    p_list.add_argument("--db", type=str, default=None)
    _add_json(p_list)

    # `tether stats`
    p_stats = sub.add_parser(
        "stats",
        help="Show telemetry scorecard, cumulative token cost, and ACI friction offenders",
    )
    p_stats.add_argument("--model", type=str, default=None, help="Filter by model identifier")
    p_stats.add_argument("--skill", type=str, default=None, help="Filter by skill name")
    p_stats.add_argument("--limit", type=int, default=100, help="Max recent sessions to analyze")
    p_stats.add_argument("--db", type=str, default=None)
    _add_json(p_stats)

    # `tether retro`
    p_retro = sub.add_parser(
        "retro", help="Distill friction in a finished session into <=2 short Skill rules"
    )
    p_retro.add_argument("session_id", help="Session ID")
    p_retro.add_argument(
        "--apply", action="store_true", help="Write rules (SKILL.md or project pin)"
    )
    p_retro.add_argument("--model", type=str, default=None, help="Model for the single LLM pass")
    p_retro.add_argument("--db", type=str, default=None)

    # `tether diff`
    p_diff = sub.add_parser("diff", help="Show what the session changed in its files")
    p_diff.add_argument("session_id", help="Session ID")
    p_diff.add_argument("--stat", action="store_true", help="Added/removed line counts per file")
    p_diff.add_argument("--db", type=str, default=None)

    # `tether events`
    p_events = sub.add_parser("events", help="Print session turn events as JSONL")
    p_events.add_argument("session_id", help="Session ID")
    p_events.add_argument("--follow", action="store_true", help="Stream until the session ends")
    p_events.add_argument("--db", type=str, default=None)

    # `tether misses`
    p_miss = sub.add_parser("misses", help="List unparsed model replies as fixture-ready JSONL")
    p_miss.add_argument("session_id", nargs="?", default=None, help="Limit to one session")
    p_miss.add_argument("--model", type=str, default=None, help="Only sessions of this model")
    p_miss.add_argument("--limit", type=int, default=20, help="Max replies (default 20)")
    p_miss.add_argument("--db", type=str, default=None)
    _add_json(p_miss)

    # `tether mcp`
    p_mcp = sub.add_parser("mcp", help="Serve Tether as an MCP server over stdio")
    p_mcp.add_argument("--db", type=str, default=None)
    p_mcp.add_argument(
        "--workspace", type=str, default=None, help="Workspace root (default: current directory)"
    )

    # `tether export`
    p_export = sub.add_parser("export", help="Print a session as a Markdown transcript")
    p_export.add_argument("session_id")
    p_export.add_argument("--db", type=str, default=None, help="SQLite DB path")
    p_export.add_argument(
        "--out", type=str, default=None, help="Write to this file instead of stdout"
    )
    # `tether doctor`
    p_doctor = sub.add_parser("doctor", help="Check the local setup and say what to fix")
    p_doctor.add_argument("--model", type=str, default="ollama/qwen3.5:9b")
    p_doctor.add_argument("--db", type=str, default=".tether/tether.db")
    # `tether replay`
    p_replay = sub.add_parser("replay", help="Re-run a session's goal and compare the runs")
    p_replay.add_argument(
        "session_id", help="Session ID to replay (plain replay runs in the current directory)"
    )
    p_replay.add_argument("--model", type=str, default=None, help="Model (default: original's)")
    p_replay.add_argument(
        "--max-steps", type=_positive_int, default=None, help="Step budget (default: original's)"
    )
    p_replay.add_argument(
        "--worktree", action="store_true", help="Run in a git worktree on tether/<id>"
    )
    p_replay.add_argument("--worktree-from", help="Base ref for --worktree (default HEAD)")
    p_replay.add_argument(
        "--setup", help="Shell command run in the worktree before the model starts"
    )
    p_replay.add_argument("--db", type=str, default=None)
    _add_json(p_replay)

    # Internal `_worker`
    p_worker = sub.add_parser("_worker")
    p_worker.add_argument("session_id")
    p_worker.add_argument("--db", type=str, default=None)

    return parser


def _finish(rec: SessionRecord, ns: argparse.Namespace) -> int:
    """Print a finished session per --json/--result-file and return its exit code."""
    code = api.exit_code(rec)
    failed = api.failure_info(rec) is not None
    if getattr(ns, "result_file", None) and rec.result and not failed:
        Path(ns.result_file).write_text(rec.result, encoding="utf-8")
    if ns.json:
        print(json.dumps(api.session_dict(rec)))
    elif rec.status == "WAITING_INPUT" and rec.sandbox_config.get("approval"):
        # A request for the caller, not a deliverable: stderr, so stdout stays clean (#59).
        print(rec.result or "", file=sys.stderr)
        print(
            f"approve: tether send {rec.id} approve (or tether allow {rec.id}); "
            f"refuse: tether send {rec.id} deny",
            file=sys.stderr,
        )
    elif rec.result and failed:
        print(rec.result, file=sys.stderr)
    elif rec.result and not getattr(ns, "result_file", None):
        print(rec.result)
    return code


def _positive_int(text: str) -> int:
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError(f"must be at least 1, got {value}")
    return value


def _compare_row(rec: SessionRecord) -> dict[str, object]:
    return {
        "id": rec.id,
        "model": rec.model,
        "status": rec.status,
        "steps": rec.step_count,
        "tokens": rec.total_prompt_tokens + rec.total_completion_tokens,
        "wall_s": round(rec.updated_at - rec.created_at, 1),
    }


def _format_compare(orig: dict[str, object], rep: dict[str, object]) -> str:
    rows = [
        (label, str(orig[key]), str(rep[key]))
        for label, key in (
            ("model", "model"),
            ("status", "status"),
            ("steps", "steps"),
            ("tokens", "tokens"),
            ("wall_s (approx)", "wall_s"),
        )
    ]
    # Size each column to its longest cell so long model ids never run into the next column.
    label_w = max(len(label) for label, _, _ in rows) + 2
    orig_w = max(len("original"), *(len(o) for _, o, _ in rows)) + 2
    lines = [
        f"replay of {orig['id']} -> {rep['id']}",
        f"{'':<{label_w}}{'original':<{orig_w}}replay",
    ]
    lines.extend(f"{label:<{label_w}}{o:<{orig_w}}{r}" for label, o, r in rows)
    return "\n".join(lines)


def _sandbox_from_ns(
    ns: argparse.Namespace, web_allow: tuple[str, ...] | None
) -> SandboxPolicy | None:
    """Build the SandboxPolicy for run/pipeline; print the error and return None on bad input."""
    try:
        allow_outside = parse_allow_outside(ns.allow)
    except ValueError as exc:
        print(f"Error: --allow: {exc}", file=sys.stderr)
        return None
    try:
        limits = parse_limits(ns.limit)
    except ValueError as exc:
        print(f"Error: --limit: {exc}", file=sys.stderr)
        return None
    try:
        return SandboxPolicy(
            profile=ns.sandbox,
            workspace_root=Path.cwd(),
            network=not ns.no_network,
            web_allow=web_allow,
            allow_unsandboxed=ns.allow_unsandboxed,
            allow_outside=allow_outside,
            limits=limits,
        )
    except ValueError as exc:
        label = "--limit: " if limits and str(exc).startswith("limit ") else ""
        print(f"Error: {label}{exc}", file=sys.stderr)
        return None


async def _replay(ns: argparse.Namespace) -> int:
    """Re-run a session's goal with its saved setup and print a comparison."""
    if not ns.worktree and (ns.setup or ns.worktree_from):
        print("Error: --setup and --worktree-from need --worktree", file=sys.stderr)
        return 2
    if ns.model is not None and not ns.model.strip():
        print(
            "Error: --model must not be empty. Omit it to use the original's model.",
            file=sys.stderr,
        )
        return 1
    orig = Harness(db_path=ns.db).store.get_session(ns.session_id)
    if orig is None:
        print(
            f"Error: session {ns.session_id} not found. List ids with tether list.",
            file=sys.stderr,
        )
        return 1
    if orig.status in ("RUNNING", "WAITING_INPUT"):
        print(
            f"Error: session {orig.id} is still {orig.status}. "
            f"Wait for it or run tether stop {orig.id}, then replay.",
            file=sys.stderr,
        )
        return 1
    try:
        harness = Harness.from_session(
            orig,
            db_path=ns.db,
            model=ns.model,
            max_steps=ns.max_steps,
            worktree=ns.worktree,
            worktree_from=ns.worktree_from,
            setup=ns.setup,
        )
        rep = await harness.run(orig.goal, parent_id=orig.id)
    except WorktreeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Error: replay failed: {exc}. Check --model and provider keys.", file=sys.stderr)
        return 1
    if ns.json:
        print(json.dumps({"original": _compare_row(orig), "replay": _compare_row(rep)}))
    else:
        print(_format_compare(_compare_row(orig), _compare_row(rep)))
    return 0


def _cmd_diff(ns: argparse.Namespace) -> int:
    store = SQLiteStore(db_path=ns.db)
    rec = store.get_session(ns.session_id)
    if rec is None:
        print(
            f"Error: session `{ns.session_id}` not found. Check the id with `tether list`.",
            file=sys.stderr,
        )
        return 1
    text, code = render_diff(
        store, ns.session_id, Path(rec.sandbox_config["workspace_root"]), ns.stat
    )
    print(text, end="", file=sys.stderr if code else sys.stdout)
    return code


async def _async_main(argv: list[str]) -> int:
    # Support shorthand `tether --headless "Goal"` by inserting `run` if needed
    effective_argv = list(argv)
    if (
        effective_argv
        and effective_argv[0] not in _KNOWN_SUBCOMMANDS
        and effective_argv[0] not in ("-h", "--help", "--version")
    ):
        effective_argv.insert(0, "run")

    parser = build_parser()
    if not effective_argv:
        parser.print_help()
        return 0

    if effective_argv[:1] == ["pipeline"]:
        # Intermixed parsing lets flags such as --resume/--db sit between the optional
        # positionals (pipeline_file, goal) on every supported Python version.
        sub_action = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
        ns = sub_action.choices["pipeline"].parse_intermixed_args(effective_argv[1:])
        ns.subcommand = "pipeline"
    else:
        ns = parser.parse_args(effective_argv)
    cmd = ns.subcommand

    if cmd == "_worker":
        harness = Harness(db_path=ns.db)
        await harness.execute_session(ns.session_id)
        return 0

    if cmd == "replay":
        return await _replay(ns)

    if cmd == "run":
        goal = " ".join(ns.goal).strip()
        if not ns.worktree and (ns.setup or ns.worktree_from):
            print("Error: --setup and --worktree-from need --worktree", file=sys.stderr)
            return api.EXIT_USAGE
        try:
            web_allow = parse_web_allow(ns.web_allow)
        except ValueError as exc:
            print(f"Error: --web-allow: {exc}", file=sys.stderr)
            return api.EXIT_USAGE
        sandbox = _sandbox_from_ns(ns, web_allow)
        if sandbox is None:
            return api.EXIT_USAGE
        try:
            schema = json.loads(Path(ns.output_schema).read_text()) if ns.output_schema else None
            harness = Harness(
                model=ns.model,
                skill=ns.skill,
                tools=ns.tools,
                verify=ns.verify,
                sandbox=sandbox,
                db_path=ns.db,
                max_steps=ns.max_steps,
                max_tokens=ns.max_tokens,
                output_schema=schema,
                params=parse_params(ns.param),
                max_context_tokens=ns.context_tokens,
                fold_observations_after=ns.fold_after,
                worktree=ns.worktree,
                worktree_from=ns.worktree_from,
                setup=ns.setup,
            )
        except (OSError, ValueError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return api.EXIT_USAGE
        if ns.headless:
            try:
                sid = harness.spawn(goal)
            except (WorktreeError, SandboxUnavailableError) as exc:
                print(f"Error: {exc}", file=sys.stderr)
                return api.EXIT_USAGE
            print(json.dumps({"v": api.SCHEMA_VERSION, "id": sid}) if ns.json else sid)
            return 0
        try:
            rec = harness.create_session(goal)
        except (WorktreeError, SandboxUnavailableError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return api.EXIT_USAGE
        # #90: a caller that kills a foreground run on its own timeout still has the id
        print(f"session {rec.id}", file=sys.stderr, flush=True)
        watcher = asyncio.create_task(
            watch(
                harness.store,
                rec.id,
                harness.model,
                verbose=ns.verbose,
                tty=sys.stderr.isatty() and not ns.json,
            )
        )
        await asyncio.sleep(0)  # let the watcher start so cancel reaches its cleanup
        try:
            rec = await harness.execute_session(rec.id)
        finally:
            watcher.cancel()
            await watcher
        return _finish(rec, ns)

    if cmd == "pipeline":
        if ns.resume and (ns.pipeline_file or ns.goal or ns.headless):
            print(
                "Error: --resume takes only a session id (no file, goal or --headless)",
                file=sys.stderr,
            )
            return api.EXIT_USAGE
        if not ns.resume and not (ns.pipeline_file and ns.goal):
            print(
                "Error: usage: tether pipeline <pipeline.yaml> <goal> | --resume <session_id>",
                file=sys.stderr,
            )
            return api.EXIT_USAGE
        goal = " ".join(ns.goal).strip()
        try:
            web_allow = parse_web_allow(ns.web_allow)
        except ValueError as exc:
            print(f"Error: --web-allow: {exc}", file=sys.stderr)
            return api.EXIT_USAGE
        sandbox = _sandbox_from_ns(ns, web_allow)
        if sandbox is None:
            return api.EXIT_USAGE
        try:
            harness = Harness(
                model=ns.model,
                sandbox=sandbox,
                db_path=ns.db,
                max_steps=ns.max_steps,
                max_context_tokens=ns.context_tokens,
                fold_observations_after=ns.fold_after,
            )
        except ValueError as exc:
            # A bad .tether/allow.json is a config error: loud on stderr, exit 1, no traceback.
            print(f"Error: {exc}", file=sys.stderr)
            return api.EXIT_USAGE
        try:
            if ns.resume:
                current = harness.store.get_session(ns.resume)
                if current is not None and current.status == "COMPLETED":
                    print(f"Pipeline `{ns.resume}` is already COMPLETED; nothing to resume.")
                    return 0
                print(f"Resuming pipeline `{ns.resume}`.", file=sys.stderr)
                rec = await harness.resume_pipeline(ns.resume)
            elif ns.headless:
                sid = harness.spawn_pipeline(Path(ns.pipeline_file), goal)
                print(json.dumps({"v": api.SCHEMA_VERSION, "id": sid}) if ns.json else sid)
                return 0
            else:
                rec = await harness.run_pipeline(Path(ns.pipeline_file), goal)
        except (PipelineResumeError, SandboxUnavailableError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return api.EXIT_USAGE
        except (OSError, ValueError, yaml.YAMLError) as exc:
            print(f"Error: invalid pipeline `{ns.pipeline_file}`: {exc}", file=sys.stderr)
            return api.EXIT_USAGE
        return _finish(rec, ns)

    if cmd == "doctor":
        from tether.doctor import run_checks

        host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        checks = run_checks(ns.model, host, Path(ns.db))
        for check in checks:
            status = "ok  " if check.ok else "FAIL"
            print(f"{status} {check.name}  {check.detail}")
        return 0 if all(check.ok for check in checks) else 1

    if cmd == "mcp":
        try:
            from tether.mcp import serve
        except ImportError:
            print(
                "tether: warning: MCP support is not installed. "
                "Install it with: pip install 'tether-sdk[mcp]'",
                file=sys.stderr,
            )
            return api.EXIT_USAGE

        await serve(db_path=ns.db, workspace=Path(ns.workspace or Path.cwd()))
        return 0

    if cmd == "diff":
        return _cmd_diff(ns)

    store = SQLiteStore(db_path=getattr(ns, "db", None))

    if cmd == "misses":
        if ns.session_id and not store.get_session(ns.session_id):
            print(f"Error: session `{ns.session_id}` not found.", file=sys.stderr)
            return api.EXIT_USAGE
        misses = store.list_nudges(ns.session_id, ns.model, ns.limit)
        if not misses:
            if not ns.json:
                print("No unparsed replies.")
            return 0
        for miss_sess, turn in misses:
            if ns.json:
                miss_rec = {
                    "session": miss_sess.id,
                    "model": miss_sess.model,
                    "step": turn.step,
                    "reply": turn.content,
                    "expected": None,
                }
                print(json.dumps(miss_rec))
            else:
                print(f"[{miss_sess.id} step {turn.step} {miss_sess.model}]")
                print(turn.content[:300])
        return 0

    if cmd == "events":
        if not store.get_session(ns.session_id):
            print(f"Error: session `{ns.session_id}` not found.", file=sys.stderr)
            return api.EXIT_USAGE
        last = 0
        while True:
            cur = store.get_session(ns.session_id)  # status first: no event is missed at the end
            for ev in api.events(store, ns.session_id, after_turn=last):
                last = ev["turn"]
                print(json.dumps(ev), flush=True)
            if not ns.follow or cur is None or cur.status not in ("PENDING", "RUNNING"):
                if ns.follow:
                    print(json.dumps({"event": "status", "status": cur.status if cur else None}))
                return 0
            await asyncio.sleep(0.5)

    if cmd == "status":
        srec = store.get_session(ns.session_id)
        if not srec:
            print(f"Error: session `{ns.session_id}` not found.", file=sys.stderr)
            return api.EXIT_USAGE
        if ns.json:
            print(json.dumps(api.session_dict(srec, include_result=False)))
            return 0
        turns = store.get_turns(srec.id)
        last_cmd = next((t.tool_cmd for t in reversed(turns) if t.tool_cmd), "-")
        print(
            f"{'ID':<14} {'STATUS':<13} {'MODEL':<22} {'STEP':<7} {'PEAK_TOK':<9} LAST_CMD\n"
            f"{srec.id:<14} {srec.status:<13} {srec.model:<22} "
            f"{srec.step_count}/{srec.max_steps:<4} {srec.peak_tokens:<9} {last_cmd}"
        )
        wt_line = api.worktree_line(srec)
        if wt_line:
            print(wt_line)
        if "sandbox_mode" in srec.sandbox_config:
            print(f"sandbox: {srec.sandbox_config['sandbox_mode']}")
        return 0

    if cmd == "read":
        srec = store.get_session(ns.session_id)
        if not srec:
            print(f"Error: session `{ns.session_id}` not found.", file=sys.stderr)
            return api.EXIT_USAGE
        if ns.json:
            if ns.steps:
                print(json.dumps(api.events(store, srec.id)))
            elif ns.digest:
                print(json.dumps(api.digest_dict(store, srec)))
            else:
                print(json.dumps(api.session_dict(srec)))
            return 0
        if ns.steps:
            turns = store.get_turns(srec.id)
            for t in turns:
                if t.tool_cmd:
                    print(f"[step {t.step}] act({t.tool_cmd!r})")
                else:
                    print(f"[step {t.step} {t.role}] {t.content[:200]}")
            return 0
        if ns.thinking:
            thinking_turns = [t for t in store.get_turns(srec.id) if t.thinking]
            if not thinking_turns:
                print(
                    f"no thinking recorded for session {srec.id}; "
                    "use a thinking-capable model (e.g. a reasoning model) to record thinking"
                )
                return 0
            for t in thinking_turns:
                print(f"step {t.step}: {t.thinking}")
            return 0
        if ns.digest:
            print(store.get_session_digest(srec.id))
            return 0
        print(srec.result or store.get_session_digest(srec.id))
        return 0

    if cmd == "query":
        srec = store.get_session(ns.session_id)
        if srec is None:
            print(f"Error: unknown session `{ns.session_id}`", file=sys.stderr)
            return api.EXIT_USAGE
        q = " ".join(ns.query).strip()
        hits = store.search_chunks(q, session_ids=[ns.session_id], top_k=ns.top)
        if not hits:
            total = store.count_chunks([ns.session_id])
            if total == 0:
                print(
                    f"No chunks are indexed for `{ns.session_id}` yet "
                    "(no observations or result recorded)."
                )
            else:
                print(
                    f"No BM25 RAG chunks matched `{q}` in `{ns.session_id}` "
                    f"({total} chunks indexed). Try fewer or different words."
                )
            return 0
        for h in hits:
            print(f"[{h.session_id} {h.source_type}:{h.source_id}#{h.chunk_index}]\n{h.content}\n")
        return 0

    if cmd in ("send", "allow"):
        msg = "approve" if cmd == "allow" else " ".join(ns.message).strip()
        harness = Harness(db_path=ns.db)
        try:
            rec = await harness.send(ns.session_id, msg, headless=ns.headless)
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return api.EXIT_USAGE
        if ns.json:
            print(json.dumps(api.session_dict(rec)))
            return api.exit_code(rec)
        if ns.headless or rec.status in ("RUNNING", "PENDING"):
            print(f"Message queued for `{rec.id}` [{rec.status}].")
        else:
            print(rec.result or f"[{rec.id} {rec.status}]")
        return 0

    if cmd == "wait":
        # 6 is used by no other wait outcome; a timeout must not look like success (#269).
        exit_wait_timeout = 6
        elapsed = 0.0
        timed_out = False
        while elapsed < ns.timeout:
            records = [store.get_session(sid) for sid in ns.session_ids]
            if any(r is not None and r.status == "WAITING_INPUT" for r in records) or all(
                r is None or r.status in ("COMPLETED", "FAILED", "WAITING_INPUT") for r in records
            ):
                break
            await asyncio.sleep(0.05)
            elapsed += 0.05
        else:
            # Only a wait that ran out of time reaches here; an early break is not a timeout.
            timed_out = True
        recs = [store.get_session(sid) for sid in ns.session_ids]
        if ns.json:
            print(json.dumps([api.digest_dict(store, r) for r in recs if r]))
        else:
            for sid in ns.session_ids:
                print(store.get_session_digest(sid))
        still = [r.id for r in recs if r and r.status in ("RUNNING", "PENDING")]
        if timed_out and still:
            print(f"timed out; still RUNNING: {' '.join(still)}", file=sys.stderr)
            return exit_wait_timeout
        return max((api.exit_code(r) for r in recs if r), default=0)

    if cmd == "stop":
        srec = store.get_session(ns.session_id)
        if srec is None:
            print(f"Error: unknown session `{ns.session_id}`", file=sys.stderr)
            return api.EXIT_USAGE
        if srec.status == "RUNNING" and srec.pid and srec.pid != os.getpid():
            with contextlib.suppress(ProcessLookupError, PermissionError):
                os.kill(srec.pid, signal.SIGTERM)
            store.update_session(srec.id, status="FAILED", result="Stopped by user.")
            srec = store.get_session(srec.id) or srec
        if ns.json:
            print(json.dumps(api.session_dict(srec)))
        else:
            print(f"[{srec.id} {srec.status}]")
        return 0

    if cmd == "export":
        from tether.export import to_markdown

        try:
            text = to_markdown(store, ns.session_id)
        except KeyError:
            print(f"Error: session `{ns.session_id}` not found.", file=sys.stderr)
            return 1
        if ns.out:
            Path(ns.out).write_text(text, encoding="utf-8")
            print(ns.out)
        else:
            print(text)
        return 0

    if cmd == "list":
        sessions = store.list_sessions(limit=ns.limit)
        if ns.json:
            print(json.dumps([api.session_dict(x, include_result=False) for x in sessions]))
            return 0
        if not sessions:
            print("No sessions recorded.")
            return 0
        status_w = max(len("STATUS"), *(len(s.status) for s in sessions))
        print(f"{'ID':<14} {'STATUS':<{status_w}} {'MODEL':<22} {'STEP':<7} GOAL")
        for s in sessions:
            g = s.goal.replace("\n", " ")[:48]
            print(
                f"{s.id:<14} {s.status:<{status_w}} {s.model:<22} "
                f"{s.step_count}/{s.max_steps:<4} {g}"
            )
        return 0

    if cmd == "stats":
        if ns.json:
            print(json.dumps(api.stats_dict(store, model=ns.model, skill=ns.skill, limit=ns.limit)))
            return 0
        print(store.format_stats_report(model=ns.model, skill=ns.skill, limit=ns.limit))
        return 0

    if cmd == "retro":
        from tether.retro import run_retro

        try:
            print(await run_retro(store, ns.session_id, apply=ns.apply, model=ns.model))
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        return 0

    parser.print_help()
    return 0


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    code = asyncio.run(_async_main(args))
    if argv is None:
        raise SystemExit(code)
    return code


if __name__ == "__main__":  # pragma: no cover
    main()
