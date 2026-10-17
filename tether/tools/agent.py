"""Always-async multi-agent orchestration and SQLite FTS5 BM25 RAG (`agent`)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from tether.decorator import ToolSpec, build_tool_spec
from tether.sandbox import SandboxPolicy
from tether.skills import SkillLoader
from tether.store import SQLiteStore


def make_agent_tool(
    store: SQLiteStore,
    parent_session_id: str,
    default_model: str,
    parent_sandbox: SandboxPolicy,
    skill_loader: SkillLoader,
    worker_spawner: Callable[[str], int | None],
    wait_timeout: float = 120.0,
) -> ToolSpec:
    help_str = (
        "Usage: agent spawn [--skill s] [--model m] [--tools t] <goal> | "
        "wait <id...> | query <id|--all> <q> [--top 3] | read <id> [--full] | send <id> <msg>\n"
        "Desc : Spawn async sub-agents or query results via BM25 RAG."
    )

    async def _agent(args: list[str], stdin: str | None = None) -> str:
        if not args or args[0] in ("--help", "-h"):
            return help_str

        sub = args[0]

        if sub == "spawn":
            skill_name: str | None = None
            model_name: str | None = None
            tools_list: list[str] = []
            goal_parts: list[str] = []
            i = 1
            while i < len(args):
                if args[i] == "--skill" and i + 1 < len(args):
                    skill_name = args[i + 1]
                    i += 2
                elif args[i] == "--model" and i + 1 < len(args):
                    model_name = args[i + 1]
                    i += 2
                elif args[i] == "--tools" and i + 1 < len(args):
                    tools_list = [t.strip() for t in args[i + 1].split(",") if t.strip()]
                    i += 2
                else:
                    goal_parts.append(args[i])
                    i += 1

            goal = " ".join(goal_parts).strip() or (stdin or "").strip()
            if not goal:
                return f"Error: missing `<goal>` for `agent spawn`.\n{help_str}"

            skill_verify: list[str] = []
            if skill_name:
                sk = skill_loader.load(skill_name)
                if not sk:
                    return f"Error: skill `{skill_name}` not found."
                if not model_name and sk.model:
                    model_name = sk.model
                if not tools_list and sk.tools:
                    tools_list = list(sk.tools)
                if sk.verify:
                    skill_verify = list(sk.verify)

            child_sandbox = parent_sandbox.attenuate()
            for sv in skill_verify:
                if sv not in child_sandbox.verify_commands:
                    child_sandbox.verify_commands.append(sv)
            child = store.create_session(
                goal=goal,
                model=model_name or default_model,
                skill=skill_name,
                tools=tools_list,
                sandbox_config=child_sandbox.to_dict(),
                parent_id=parent_session_id,
            )
            worker_spawner(child.id)
            return child.id

        if sub == "status":
            if len(args) < 2:
                return f"Error: missing `<session_id>`.\n{help_str}"
            rec = store.get_session(args[1])
            if not rec:
                return f"Error: session `{args[1]}` not found."
            turns = store.get_turns(rec.id)
            last_cmd = next((t.tool_cmd for t in reversed(turns) if t.tool_cmd), "-")
            return (
                f"{rec.id} [{rec.status}] step {rec.step_count}/{rec.max_steps} | "
                f"model: {rec.model} | last: {last_cmd}"
            )

        if sub == "wait":
            target_ids = [a for a in args[1:] if not a.startswith("-")]
            if not target_ids:
                return f"Error: specify one or more session IDs to wait for.\n{help_str}"

            elapsed = 0.0
            poll_interval = 0.05
            while elapsed < wait_timeout:
                records = [store.get_session(sid) for sid in target_ids]
                if any(r is not None and r.status == "WAITING_INPUT" for r in records) or all(
                    r is None or r.status not in ("PENDING", "RUNNING") for r in records
                ):
                    break
                await asyncio.sleep(poll_interval)
                elapsed += poll_interval

            digests = [store.get_session_digest(sid) for sid in target_ids]
            return "\n\n".join(digests)

        if sub == "query":
            if len(args) < 2:
                return f"Error: usage `agent query <id|--all> <query> [--top 3]`.\n{help_str}"
            target = args[1]
            top_k = 3
            q_parts: list[str] = []
            i = 2
            while i < len(args):
                if args[i] == "--top" and i + 1 < len(args):
                    try:
                        top_k = int(args[i + 1])
                    except ValueError:
                        return "Error: `--top` expects an integer."
                    i += 2
                else:
                    q_parts.append(args[i])
                    i += 1
            query = " ".join(q_parts).strip() or (stdin or "").strip()
            if not query:
                return f"Error: missing `<query>`.\n{help_str}"

            if target == "--all":
                children = store.list_sessions(parent_id=parent_session_id)
                session_ids = [c.id for c in children]
                if not session_ids:
                    return "No child sub-agent sessions found."
            else:
                session_ids = [target]

            hits = store.search_chunks(query, session_ids=session_ids, top_k=top_k)
            if not hits:
                return f"No BM25 RAG chunks matched `{query}` in {', '.join(session_ids)}."
            blocks = [
                f"[{h.session_id} {h.source_type}:{h.source_id}#{h.chunk_index}]\n{h.content}"
                for h in hits
            ]
            return "\n\n---\n\n".join(blocks)

        if sub == "read":
            if len(args) < 2:
                return f"Error: missing `<session_id>`.\n{help_str}"
            sid = args[1]
            full = "--full" in args
            rec = store.get_session(sid)
            if not rec:
                return f"Error: session `{sid}` not found."
            if not full:
                return store.get_session_digest(sid)
            return rec.result or f"[{sid} {rec.status}: no final result yet]"

        if sub == "send":
            if len(args) < 2:
                return f"Error: missing `<session_id>`.\n{help_str}"
            sid = args[1]
            msg = " ".join(args[2:]).strip() or (stdin or "").strip()
            if not msg:
                return f"Error: missing `<message>`.\n{help_str}"
            rec = store.get_session(sid)
            if not rec:
                return f"Error: session `{sid}` not found."
            store.enqueue_inbox(sid, msg)
            if rec.status in ("WAITING_INPUT", "COMPLETED", "FAILED", "PENDING"):
                store.update_session(sid, status="PENDING")
                worker_spawner(sid)
                return f"Queued message and resumed session `{sid}`."
            return f"Queued message into running session `{sid}` inbox."

        return f"Error: unknown subcommand `{sub}`.\n{help_str}"

    return build_tool_spec(
        _agent,
        name="agent",
        description="Spawn async sub-agents and query their work via BM25 RAG",
        custom_help=help_str,
        raw_dispatch=True,
    )
