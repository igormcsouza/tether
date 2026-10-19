"""Headless CLI (`tether run|pipeline|status|read|query|send|wait|list|stats`)."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

import yaml

from tether import __version__, api
from tether.harness import Harness
from tether.sandbox import SandboxPolicy
from tether.store import SessionRecord, SQLiteStore

_KNOWN_SUBCOMMANDS = {
    "run",
    "pipeline",
    "status",
    "read",
    "query",
    "send",
    "wait",
    "list",
    "stats",
    "retro",
    "events",
    "mcp",
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
    p_run.add_argument("--max-steps", type=int, default=15, help="Max reasoning steps")
    p_run.add_argument(
        "--db", type=str, default=None, help="SQLite DB path (default .tether/tether.db)"
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
    _add_json(p_run)
    p_run.add_argument("goal", nargs="+", help="Task goal or instruction")

    # `tether pipeline`
    p_pipe = sub.add_parser(
        "pipeline",
        help="Execute a declarative multi-stage YAML workflow inline or headless",
    )
    p_pipe.add_argument("pipeline_file", help="Path to declarative pipeline YAML manifest")
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
        "--max-steps", type=int, default=15, help="Default max reasoning steps per stage"
    )
    p_pipe.add_argument(
        "--db", type=str, default=None, help="SQLite DB path (default .tether/tether.db)"
    )
    p_pipe.add_argument(
        "--result-file", type=str, default=None, help="Write the deliverable here, not to stdout"
    )
    _add_json(p_pipe)
    p_pipe.add_argument("goal", nargs="+", help="Root task goal or instruction")

    # `tether status`
    p_status = sub.add_parser("status", help="Show live session status and token metrics")
    p_status.add_argument("session_id", help="Session ID (e.g. ses_...)")
    p_status.add_argument("--db", type=str, default=None)
    _add_json(p_status)

    # `tether read`
    p_read = sub.add_parser("read", help="Read session final result, compact digest, or step log")
    p_read.add_argument("session_id", help="Session ID")
    p_read.add_argument("--digest", action="store_true", help="Show compact ~50-token digest card")
    p_read.add_argument("--steps", action="store_true", help="Show step-by-step work log")
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

    # `tether wait`
    p_wait = sub.add_parser("wait", help="Wait for one or more headless sessions to finish")
    p_wait.add_argument("session_ids", nargs="+", help="Session ID(s)")
    p_wait.add_argument("--timeout", type=float, default=120.0)
    p_wait.add_argument("--db", type=str, default=None)
    _add_json(p_wait)

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

    # `tether events`
    p_events = sub.add_parser("events", help="Print session turn events as JSONL")
    p_events.add_argument("session_id", help="Session ID")
    p_events.add_argument("--follow", action="store_true", help="Stream until the session ends")
    p_events.add_argument("--db", type=str, default=None)

    # `tether mcp`
    p_mcp = sub.add_parser("mcp", help="Serve Tether as an MCP server over stdio")
    p_mcp.add_argument("--db", type=str, default=None)
    p_mcp.add_argument(
        "--workspace", type=str, default=None, help="Workspace root (default: current directory)"
    )

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
    elif rec.result and failed:
        print(rec.result, file=sys.stderr)
    elif rec.result and not getattr(ns, "result_file", None):
        print(rec.result)
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

    ns = parser.parse_args(effective_argv)
    cmd = ns.subcommand

    if cmd == "_worker":
        harness = Harness(db_path=ns.db)
        await harness.execute_session(ns.session_id)
        return 0

    if cmd == "run":
        goal = " ".join(ns.goal).strip()
        sandbox = SandboxPolicy(
            profile=ns.sandbox, workspace_root=Path.cwd(), network=not ns.no_network
        )
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
                output_schema=schema,
            )
        except (OSError, ValueError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return api.EXIT_USAGE
        if ns.headless:
            sid = harness.spawn(goal)
            print(json.dumps({"v": api.SCHEMA_VERSION, "id": sid}) if ns.json else sid)
            return 0
        return _finish(await harness.run(goal), ns)

    if cmd == "pipeline":
        goal = " ".join(ns.goal).strip()
        sandbox = SandboxPolicy(
            profile=ns.sandbox, workspace_root=Path.cwd(), network=not ns.no_network
        )
        harness = Harness(
            model=ns.model,
            sandbox=sandbox,
            db_path=ns.db,
            max_steps=ns.max_steps,
        )
        try:
            if ns.headless:
                sid = harness.spawn_pipeline(Path(ns.pipeline_file), goal)
                print(json.dumps({"v": api.SCHEMA_VERSION, "id": sid}) if ns.json else sid)
                return 0
            rec = await harness.run_pipeline(Path(ns.pipeline_file), goal)
        except (OSError, ValueError, yaml.YAMLError) as exc:
            print(f"Error: invalid pipeline `{ns.pipeline_file}`: {exc}", file=sys.stderr)
            return api.EXIT_USAGE
        return _finish(rec, ns)

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

    store = SQLiteStore(db_path=getattr(ns, "db", None))

    if cmd == "events":
        if not store.get_session(ns.session_id):
            print(f"Error: session `{ns.session_id}` not found.", file=sys.stderr)
            return api.EXIT_USAGE
        last = 0
        while True:
            for ev in api.events(store, ns.session_id, after_turn=last):
                last = ev["turn"]
                print(json.dumps(ev), flush=True)
            cur = store.get_session(ns.session_id)
            if not ns.follow or cur is None or cur.status not in ("PENDING", "RUNNING"):
                if ns.follow:  # final drain after the terminal status was observed
                    for ev in api.events(store, ns.session_id, after_turn=last):
                        print(json.dumps(ev), flush=True)
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
        if ns.digest:
            print(store.get_session_digest(srec.id))
            return 0
        print(srec.result or store.get_session_digest(srec.id))
        return 0

    if cmd == "query":
        q = " ".join(ns.query).strip()
        hits = store.search_chunks(q, session_ids=[ns.session_id], top_k=ns.top)
        if not hits:
            print(f"No BM25 RAG chunks matched `{q}`.")
            return 0
        for h in hits:
            print(f"[{h.session_id} {h.source_type}:{h.source_id}#{h.chunk_index}]\n{h.content}\n")
        return 0

    if cmd == "send":
        msg = " ".join(ns.message).strip()
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
        elapsed = 0.0
        while elapsed < ns.timeout:
            records = [store.get_session(sid) for sid in ns.session_ids]
            if any(r is not None and r.status == "WAITING_INPUT" for r in records) or all(
                r is None or r.status in ("COMPLETED", "FAILED", "WAITING_INPUT") for r in records
            ):
                break
            await asyncio.sleep(0.05)
            elapsed += 0.05
        recs = [store.get_session(sid) for sid in ns.session_ids]
        if ns.json:
            print(json.dumps([api.digest_dict(store, r) for r in recs if r]))
        else:
            for sid in ns.session_ids:
                print(store.get_session_digest(sid))
        return max((api.exit_code(r) for r in recs if r), default=0)

    if cmd == "list":
        sessions = store.list_sessions(limit=ns.limit)
        if ns.json:
            print(json.dumps([api.session_dict(x, include_result=False) for x in sessions]))
            return 0
        if not sessions:
            print("No sessions recorded.")
            return 0
        print(f"{'ID':<14} {'STATUS':<10} {'MODEL':<22} {'STEP':<7} GOAL")
        for s in sessions:
            g = s.goal.replace("\n", " ")[:48]
            print(f"{s.id:<14} {s.status:<10} {s.model:<22} {s.step_count}/{s.max_steps:<4} {g}")
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


def main(argv: list[str] | None = None) -> None:
    args = sys.argv[1:] if argv is None else argv
    code = asyncio.run(_async_main(args))
    if argv is None:
        raise SystemExit(code)


if __name__ == "__main__":  # pragma: no cover
    main()
