"""Working scratchpad (`pin`/`unpin`), FTS5 BM25 RAG (`search`), and observation `recall`."""

from __future__ import annotations

from tether.decorator import ToolSpec, build_tool_spec
from tether.store import GLOBAL_SESSION_ID, SQLiteStore


def make_mem_tool(store: SQLiteStore, session_id: str) -> ToolSpec:
    help_str = (
        "Usage: mem pin [--project] <key> <val> | mem unpin [--project] <key> | "
        "mem search [--project] <query> [--obs id] [--top 3] | mem recall <obs_id>\n"
        "Desc : Pin session/project facts, BM25-search memory, or recall raw output."
    )

    def _mem(args: list[str], stdin: str | None = None) -> str:
        if not args or args[0] in ("--help", "-h"):
            return help_str

        sub = args[0]
        if sub == "pin":
            is_project = False
            positional: list[str] = []
            for arg in args[1:]:
                if arg in ("--project", "--all"):
                    is_project = True
                else:
                    positional.append(arg)
            if not positional:
                return f"Error: missing `<key>`.\n{help_str}"
            key = positional[0]
            val = " ".join(positional[1:]).strip() if len(positional) > 1 else (stdin or "").strip()
            if not val:
                return f"Error: missing `<val>` (pass inline or via `stdin`).\n{help_str}"
            target_sid = GLOBAL_SESSION_ID if is_project else session_id
            store.set_pin(target_sid, key, val)
            return f"Pinned `{key}` (project)." if is_project else f"Pinned `{key}`."

        if sub == "unpin":
            is_project = False
            positional = []
            for arg in args[1:]:
                if arg in ("--project", "--all"):
                    is_project = True
                else:
                    positional.append(arg)
            if not positional:
                return f"Error: missing `<key>`.\n{help_str}"
            key = positional[0]
            target_sid = GLOBAL_SESSION_ID if is_project else session_id
            removed = store.remove_pin(target_sid, key)
            return f"Unpinned `{key}`." if removed else f"Key `{key}` not found."

        if sub == "list":
            is_project = any(a in ("--project", "--all") for a in args[1:])
            target_sid = GLOBAL_SESSION_ID if is_project else session_id
            pins = store.get_pins(target_sid)
            if not pins:
                return "No pinned facts."
            return "\n".join(f"- {k}: {v}" for k, v in pins.items())

        if sub == "search":
            is_project = False
            obs_filter: str | None = None
            top_k = 3
            q_parts: list[str] = []
            i = 1
            while i < len(args):
                if args[i] in ("--project", "--all"):
                    is_project = True
                    i += 1
                elif args[i] == "--obs" and i + 1 < len(args):
                    obs_filter = args[i + 1]
                    i += 2
                elif args[i] == "--top" and i + 1 < len(args):
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
            if is_project:
                hits = store.search_project_chunks(
                    query,
                    source_id=obs_filter,
                    top_k=top_k,
                )
            else:
                hits = store.search_chunks(
                    query,
                    session_ids=[session_id],
                    source_id=obs_filter,
                    top_k=top_k,
                )
            if not hits:
                return f"No matching chunks for `{query}`."
            if is_project:
                formatted = [
                    f"[{h.session_id} {h.source_type}:{h.source_id}#{h.chunk_index}]\n{h.content}"
                    for h in hits
                ]
            else:
                formatted = [
                    f"[{h.source_type}:{h.source_id}#{h.chunk_index}]\n{h.content}" for h in hits
                ]
            return "\n\n---\n\n".join(formatted)

        if sub == "recall":
            if len(args) < 2:
                return f"Error: missing `<obs_id>`.\n{help_str}"
            obs = store.get_observation(session_id, args[1])
            if not obs:
                return f"Error: observation `{args[1]}` not found."
            return f"[{obs.id} `{obs.cmd}`]\n{obs.raw_output}"

        return f"Error: unknown subcommand `{sub}`.\n{help_str}"

    return build_tool_spec(
        _mem,
        name="mem",
        description="Pin working memory facts or BM25-search/recall folded observations",
        custom_help=help_str,
        raw_dispatch=True,
    )
