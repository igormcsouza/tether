"""Headless CLI (`tether run|pipeline|status|read|query|send|wait|list|stats`)."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

import yaml

from tether.harness import Harness
from tether.sandbox import SandboxPolicy
from tether.store import SQLiteStore

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
    "_worker",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tether",
        description="Tether: Headless-first LLM-Native Micro-Harness",
    )
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
    p_run.add_argument("--max-steps", type=int, default=15, help="Max reasoning steps")
    p_run.add_argument(
        "--db", type=str, default=None, help="SQLite DB path (default .tether/tether.db)"
    )
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
        "--max-steps", type=int, default=15, help="Default max reasoning steps per stage"
    )
    p_pipe.add_argument(
        "--db", type=str, default=None, help="SQLite DB path (default .tether/tether.db)"
    )
    p_pipe.add_argument("goal", nargs="+", help="Root task goal or instruction")

    # `tether status`
    p_status = sub.add_parser("status", help="Show live session status and token metrics")
    p_status.add_argument("session_id", help="Session ID (e.g. ses_...)")
    p_status.add_argument("--db", type=str, default=None)

    # `tether read`
    p_read = sub.add_parser("read", help="Read session final result, compact digest, or step log")
    p_read.add_argument("session_id", help="Session ID")
    p_read.add_argument("--digest", action="store_true", help="Show compact ~50-token digest card")
    p_read.add_argument("--steps", action="store_true", help="Show step-by-step work log")
    p_read.add_argument("--db", type=str, default=None)

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
    p_send.add_argument("message", nargs="+", help="Follow-up instruction")

    # `tether wait`
    p_wait = sub.add_parser("wait", help="Wait for one or more headless sessions to finish")
    p_wait.add_argument("session_ids", nargs="+", help="Session ID(s)")
    p_wait.add_argument("--timeout", type=float, default=120.0)
    p_wait.add_argument("--db", type=str, default=None)

    # `tether list`
    p_list = sub.add_parser("list", help="List recent sessions")
    p_list.add_argument("--limit", type=int, default=20)
    p_list.add_argument("--db", type=str, default=None)

    # `tether stats`
    p_stats = sub.add_parser(
        "stats",
        help="Show telemetry scorecard, cumulative token cost, and ACI friction offenders",
    )
    p_stats.add_argument("--model", type=str, default=None, help="Filter by model identifier")
    p_stats.add_argument("--skill", type=str, default=None, help="Filter by skill name")
    p_stats.add_argument("--limit", type=int, default=100, help="Max recent sessions to analyze")
    p_stats.add_argument("--db", type=str, default=None)

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

    # Internal `_worker`
    p_worker = sub.add_parser("_worker")
    p_worker.add_argument("session_id")
    p_worker.add_argument("--db", type=str, default=None)

    return parser


async def _async_main(argv: list[str]) -> int:
    # Support shorthand `tether --headless "Goal"` by inserting `run` if needed
    effective_argv = list(argv)
    if (
        effective_argv
        and effective_argv[0] not in _KNOWN_SUBCOMMANDS
        and effective_argv[0] not in ("-h", "--help")
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
        sandbox = SandboxPolicy(profile=ns.sandbox, workspace_root=Path.cwd())
        harness = Harness(
            model=ns.model,
            skill=ns.skill,
            tools=ns.tools,
            verify=ns.verify,
            sandbox=sandbox,
            db_path=ns.db,
            max_steps=ns.max_steps,
        )
        if ns.headless:
            sid = harness.spawn(goal)
            print(sid)
            return 0
        rec = await harness.run(goal)
        if rec.result:
            print(rec.result)
        return 0 if rec.status in ("COMPLETED", "WAITING_INPUT") else 1

    if cmd == "pipeline":
        goal = " ".join(ns.goal).strip()
        sandbox = SandboxPolicy(profile=ns.sandbox, workspace_root=Path.cwd())
        harness = Harness(
            model=ns.model,
            sandbox=sandbox,
            db_path=ns.db,
            max_steps=ns.max_steps,
        )
        try:
            if ns.headless:
                sid = harness.spawn_pipeline(Path(ns.pipeline_file), goal)
                print(sid)
                return 0
            rec = await harness.run_pipeline(Path(ns.pipeline_file), goal)
        except (OSError, ValueError, yaml.YAMLError) as exc:
            print(f"Error: invalid pipeline `{ns.pipeline_file}`: {exc}", file=sys.stderr)
            return 1
        if rec.result:
            print(rec.result)
        return 0 if rec.status in ("COMPLETED", "WAITING_INPUT") else 1

    store = SQLiteStore(db_path=getattr(ns, "db", None))

    if cmd == "status":
        srec = store.get_session(ns.session_id)
        if not srec:
            print(f"Error: session `{ns.session_id}` not found.", file=sys.stderr)
            return 1
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
            return 1
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
            return 1
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
        for sid in ns.session_ids:
            print(store.get_session_digest(sid))
        return 0

    if cmd == "list":
        sessions = store.list_sessions(limit=ns.limit)
        if not sessions:
            print("No sessions recorded.")
            return 0
        print(f"{'ID':<14} {'STATUS':<10} {'MODEL':<22} {'STEP':<7} GOAL")
        for s in sessions:
            g = s.goal.replace("\n", " ")[:48]
            print(f"{s.id:<14} {s.status:<10} {s.model:<22} {s.step_count}/{s.max_steps:<4} {g}")
        return 0

    if cmd == "stats":
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
