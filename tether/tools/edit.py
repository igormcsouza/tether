"""Workspace-jailed file viewing and stdin patching tool (`edit`)."""

from __future__ import annotations

import ast
import difflib
import re

from tether.decorator import ToolSpec, build_tool_spec
from tether.sandbox import SandboxPolicy

# The closing marker is optional at the very end: models often stop after the new text.
_BLOCK_RE = re.compile(r"<<<<<<< SEARCH\n(.*?)\n=======\n(.*?)\n?(?:>>>>>>> REPLACE|\Z)", re.DOTALL)


def _apply_blocks(text: str, stdin: str) -> str | tuple[str, int]:
    """Apply SEARCH/REPLACE blocks atomically; each SEARCH must match exactly once."""
    blocks = _BLOCK_RE.findall(stdin)
    if not blocks:
        return "no complete `<<<<<<< SEARCH` / `=======` / `>>>>>>> REPLACE` block in stdin."
    for i, (old, new) in enumerate(blocks, 1):
        if "<<<<<<< SEARCH" in new:
            return f"SEARCH block {i} is missing its `>>>>>>> REPLACE` line; nothing changed."
        n = text.count(old)
        if n != 1:
            how = "not found (exact text, incl. indentation)" if n == 0 else f"matches {n} times"
            return (
                f"SEARCH block {i} {how}; nothing changed. First line: `{old.splitlines()[0][:60]}`"
            )
        text = text.replace(old, new, 1)
    return text, len(blocks)


def _syntax_warning(path: str, old: str | None, new: str) -> str:
    """Tell the model when its edit broke a previously valid .py file (bad indentation, etc.)."""
    if not path.endswith(".py"):
        return ""
    try:
        ast.parse(new)
        return ""
    except SyntaxError as exc:
        try:
            ast.parse(old or "")
        except SyntaxError:
            return ""  # already broken before this edit
        return f" WARNING: `{path}` no longer parses: {exc.msg} at line {exc.lineno}. Fix it now."


_PATCH_FILE_RE = re.compile(r"\*\*\* (Update|Add|Delete) File: (.+)")


def _patch_hunks(body: list[str]) -> list[tuple[list[str], list[str]]]:
    """Split an `Update File` body into (old, new) line blocks; `@@` starts a new hunk."""
    hunks: list[tuple[list[str], list[str]]] = [([], [])]
    for line in body:
        if line.startswith("@@"):
            if hunks[-1] != ([], []):
                hunks.append(([], []))
            continue
        old, new = hunks[-1]
        if line.startswith("-"):
            old.append(line[1:])
        elif line.startswith("+"):
            new.append(line[1:])
        else:  # context (a leading space is optional: models drop it)
            text = line[1:] if line.startswith(" ") else line
            old.append(text)
            new.append(text)
    return [h for h in hunks if h != ([], [])]


_UNIFIED_RE = re.compile(r"^--- .+\n\+\+\+ .+\n@@", re.M)


def _unified_to_patch(diff: str) -> str:
    """Rewrite a `git diff` / `diff -u` as a V4A patch so one applier handles both."""
    out = ["*** Begin Patch"]
    for line in diff.strip("\n").splitlines():
        if line.startswith("+++ "):
            name = line[4:].split("\t")[0].strip()
            name = name[2:] if name[:2] in ("a/", "b/") else name
            out.append(f"*** Update File: {name}")
        elif line.startswith(("--- ", "diff --git", "index ", "\\")):
            continue
        else:
            out.append(line)
    return "\n".join([*out, "*** End Patch"])


def _apply_patch(sandbox: SandboxPolicy, patch: str) -> str:
    """Apply an `*** Begin Patch` (Codex/V4A) or unified-diff patch; all-or-nothing per call."""
    if _UNIFIED_RE.search(patch):
        patch = _unified_to_patch(patch)
    lines = patch.strip("\n").splitlines()
    if not lines or lines[0].strip() != "*** Begin Patch":
        return "Error: apply_patch needs a patch starting with `*** Begin Patch` in stdin."
    sections: list[tuple[str, str, list[str]]] = []
    for line in lines[1:]:
        if line.strip() == "*** End Patch":
            break
        m = _PATCH_FILE_RE.fullmatch(line.strip())
        if m:
            sections.append((m.group(1), m.group(2).strip(), []))
        elif sections:
            sections[-1][2].append(line)
    if not sections:
        return "Error: patch has no `*** Update File:` / `*** Add File:` / `*** Delete File:`."
    staged: list[tuple[str, str, str | None]] = []  # (path, verb, new text)
    for verb, name, body in sections:
        target = sandbox.resolve_safe_path(name, write=True)
        if verb == "Delete":
            staged.append((name, verb, None))
        elif verb == "Add":
            staged.append((name, verb, "\n".join(ln[1:] for ln in body) + "\n"))
        else:
            if not target.is_file():
                return f"Error: file `{name}` not found; nothing changed."
            text = target.read_text(encoding="utf-8", errors="replace")
            for i, (old_lines, new_lines) in enumerate(_patch_hunks(body), 1):
                old_s, new_s = "\n".join(old_lines), "\n".join(new_lines)
                if not old_s:
                    text = text + ("" if text.endswith("\n") else "\n") + new_s + "\n"
                elif text.count(old_s) != 1:
                    n = text.count(old_s)
                    how = "not found" if n == 0 else f"matches {n} times"
                    return (
                        f"Error: hunk {i} of `{name}` {how}; nothing changed. "
                        f"First line: `{old_lines[0][:60]}`"
                    )
                else:
                    text = text.replace(old_s, new_s, 1)
            staged.append((name, verb, text))
    notes: list[str] = []
    for name, _verb, final in staged:
        dest = sandbox.resolve_safe_path(name, write=True)
        if final is None:
            dest.unlink(missing_ok=True)
        else:
            before = dest.read_text(encoding="utf-8", errors="replace") if dest.is_file() else None
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(final, encoding="utf-8")
            notes.append(_syntax_warning(name, before, final))
    done = ", ".join(f"{v.lower()} {n}" for n, v, _ in staged)
    return f"Patched: {done}." + "".join(notes)


_VERBS = ("view", "write", "replace", "apply_patch")


def _infer_verb(args: list[str], stdin: str | None) -> list[str]:
    """Accept `edit <path> [stdin]` and `edit --path P [--line_start a --line_end b]`.

    Models skip the verb: no stdin -> view, SEARCH/REPLACE blocks -> replace, other stdin -> write.
    """
    if args[0] in _VERBS:
        return args
    if args[0] == "--path" and len(args) >= 2:
        flags = dict(zip(args[2::2], args[3::2], strict=False))
        rng = (
            ["--lines", f"{flags['--line_start']}:{flags.get('--line_end', flags['--line_start'])}"]
            if "--line_start" in flags
            else []
        )
        return _infer_verb([args[1], *rng], stdin)
    if args[0].startswith("-") or not ("." in args[0] or "/" in args[0]):
        return args
    if stdin is None:
        return ["view", *args]
    if _UNIFIED_RE.match(stdin.lstrip()):  # a diff as stdin would otherwise overwrite the file
        return ["apply_patch"]
    return ["replace" if "<<<<<<< SEARCH" in stdin else "write", *args]


def _parse_line_range(spec: str, total_lines: int) -> tuple[int, int] | str:
    if ":" not in spec:
        try:
            n = int(spec)
            return max(1, n), min(total_lines, n)
        except ValueError:
            return f"invalid line range `{spec}` (expected `start:end`)."
    left, right = spec.split(":", 1)
    try:
        start = int(left) if left else 1
        end = int(right) if right else total_lines
    except ValueError:
        return f"invalid line range `{spec}` (expected integers `start:end`)."
    start = max(1, start)
    end = min(max(start, end), max(1, total_lines))
    return start, end


def make_edit_tool(sandbox: SandboxPolicy) -> ToolSpec:
    help_str = (
        "Usage: edit view <path> [--lines a:b] | edit write <path> [stdin] | "
        "edit replace <path> --lines a:b [stdin]\n"
        "Desc : View, write file, or replace lines. Or stdin `<<<<<<< SEARCH`/`=======`/"
        "`>>>>>>> REPLACE` blocks (exact text; no --lines)."
    )

    def _edit(args: list[str], stdin: str | None = None) -> str:
        if not args or args[0] in ("--help", "-h"):
            return help_str

        args = _infer_verb(args, stdin)
        sub = args[0]
        if sub == "apply_patch":
            return _apply_patch(sandbox, stdin or "")
        if sub == "view":
            if len(args) < 2:
                return f"Error: missing `<path>`.\n{help_str}"
            target = sandbox.resolve_safe_path(args[1], write=False)
            if not target.is_file():
                return f"Error: file `{args[1]}` not found."
            lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
            start, end = 1, min(len(lines), 100)
            if "--lines" in args:
                idx = args.index("--lines")
                if idx + 1 >= len(args):
                    return f"Error: `--lines` requires `start:end`.\n{help_str}"
                rng = _parse_line_range(args[idx + 1], len(lines))
                if isinstance(rng, str):
                    return f"Error: {rng}"
                start, end = rng
            numbered = [f"{i:4d}: {lines[i - 1]}" for i in range(start, end + 1)]
            header = f"[{args[1]} lines {start}-{end} of {len(lines)}]"
            return "\n".join([header, *numbered])

        if sub == "write":
            if len(args) < 2:
                return f"Error: missing `<path>`.\n{help_str}"
            if stdin is None:
                return f"Error: `edit write` requires file content in `stdin`.\n{help_str}"
            target = sandbox.resolve_safe_path(args[1], write=True)
            old_text = (
                target.read_text(encoding="utf-8", errors="replace") if target.is_file() else None
            )
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(stdin, encoding="utf-8")
            if old_text is None:
                line_cnt = len(stdin.splitlines())
                return f"Wrote {len(stdin):,} chars ({line_cnt} lines) to `{args[1]}`."
            old_lines = old_text.splitlines()
            new_lines = stdin.splitlines()
            ops = difflib.SequenceMatcher(a=old_lines, b=new_lines, autojunk=False).get_opcodes()
            removed = sum(i2 - i1 for tag, i1, i2, _, _ in ops if tag != "equal")
            added = sum(j2 - j1 for tag, _, _, j1, j2 in ops if tag != "equal")
            first = next(
                (old_lines[i1] for tag, i1, i2, _, _ in ops if tag != "equal" and i2 > i1),
                "none",
            )
            n_old, n_new = len(old_lines), len(new_lines)
            tail = f"{removed} removed, {added} added; first removed: {str(first).strip()[:60]}"
            if removed == added == 0 and old_text != stdin:
                tail = "only whitespace/newline changes"
            summary = f"Replaced {n_old} line{'s' * (n_old != 1)} with {n_new} ({tail})"
            if len(new_lines) < len(old_lines):
                summary += (
                    " File shrank; for partial changes use `edit replace <path> --lines a:b`."
                )
            return summary + _syntax_warning(args[1], old_text, stdin)

        if sub == "replace":
            if len(args) >= 2 and "--lines" not in args and stdin and "<<<<<<< SEARCH" in stdin:
                target = sandbox.resolve_safe_path(args[1], write=True)
                if not target.is_file():
                    return f"Error: file `{args[1]}` not found."
                old_text = target.read_text(encoding="utf-8", errors="replace")
                res = _apply_blocks(old_text, stdin)
                if isinstance(res, str):
                    return f"Error: {res}"
                target.write_text(res[0], encoding="utf-8")
                return f"Replaced {res[1]} block(s) in `{args[1]}`." + _syntax_warning(
                    args[1], old_text, res[0]
                )
            if len(args) < 2 or "--lines" not in args:
                return (
                    f"Error: `edit replace` requires `<path> --lines start:end` "
                    f"and `stdin`.\n{help_str}"
                )
            if stdin is None:
                return f"Error: `edit replace` requires replacement block in `stdin`.\n{help_str}"
            target = sandbox.resolve_safe_path(args[1], write=True)
            if not target.is_file():
                return f"Error: file `{args[1]}` not found."
            idx = args.index("--lines")
            if idx + 1 >= len(args):
                return f"Error: `--lines` requires `start:end`.\n{help_str}"
            lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
            rng = _parse_line_range(args[idx + 1], len(lines))
            if isinstance(rng, str):
                return f"Error: {rng}"
            start, end = rng
            replacement_lines = stdin.splitlines()
            updated = lines[: start - 1] + replacement_lines + lines[end:]
            new_text = "\n".join(updated) + ("\n" if stdin.endswith("\n") or lines else "")
            old_text = "\n".join(lines)
            target.write_text(new_text, encoding="utf-8")
            return (
                f"Replaced lines {start}:{end} in `{args[1]}` with {len(replacement_lines)} lines."
                + _syntax_warning(args[1], old_text, new_text)
            )

        return f"Error: unknown subcommand `{sub}`.\n{help_str}"

    return build_tool_spec(
        _edit,
        name="edit",
        description="View, create, or patch workspace files via stdin",
        custom_help=help_str,
        raw_dispatch=True,
    )
