"""Working scratchpad (`pin`/`unpin`), FTS5 BM25 RAG (`search`), and observation `recall`."""

from __future__ import annotations

from tether.decorator import ToolSpec, build_tool_spec
from tether.store import SQLiteStore


def make_mem_tool(store: SQLiteStore, session_id: str) -> ToolSpec:
    help_str = (
        "Usage: mem pin <key> <val> | mem unpin <key> | mem search <query> [--obs id] [--top 3] | "
        "mem recall <obs_id>\n"
        "Desc : Pin facts, search folded observations via BM25, or recall raw output."
    )

    def _mem(args: list[str], stdin: str | None = None) -> str:
        if not args or args[0] in ("--help", "-h"):
            return help_str

        sub = args[0]
        if sub == "pin":
            if len(args) < 2:
                return f"Error: missing `<key>`.\n{help_str}"
            key = args[1]
            val = " ".join(args[2:]).strip() if len(args) > 2 else (stdin or "").strip()
            if not val:
                return f"Error: missing `<val>` (pass inline or via `stdin`).\n{help_str}"
            store.set_pin(session_id, key, val)
            return f"Pinned `{key}`."

        if sub == "unpin":
            if len(args) < 2:
                return f"Error: missing `<key>`.\n{help_str}"
            removed = store.remove_pin(session_id, args[1])
            return f"Unpinned `{args[1]}`." if removed else f"Key `{args[1]}` not found."

        if sub == "list":
            pins = store.get_pins(session_id)
            if not pins:
                return "No pinned facts."
            return "\n".join(f"- {k}: {v}" for k, v in pins.items())

        if sub == "search":
            obs_filter: str | None = None
            top_k = 3
            q_parts: list[str] = []
            i = 1
            while i < len(args):
                if args[i] == "--obs" and i + 1 < len(args):
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
            hits = store.search_chunks(
                query,
                session_ids=[session_id],
                source_id=obs_filter,
                top_k=top_k,
            )
            if not hits:
                return f"No matching chunks for `{query}`."
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
