"""Control Plane: Tether Harness, bounded agent loop, live SQLite inbox, and headless spawner."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from tether.context import ACT_TOOL_SCHEMA, ContextAssembler, estimate_messages_tokens
from tether.decorator import ToolSpec, build_tool_spec
from tether.multiplexer import Multiplexer
from tether.providers import ModelProvider, resolve_provider
from tether.sandbox import SandboxPolicy
from tether.skills import Skill, SkillLoader, make_skill_tool
from tether.store import SessionRecord, SQLiteStore
from tether.tools import (
    ALL_BUILTIN_TOOLS,
    make_agent_tool,
    make_bash_tool,
    make_done_tool,
    make_edit_tool,
    make_mem_tool,
    make_web_tool,
)


def spawn_detached_worker(db_path: Path, session_id: str) -> int:
    """Spawn a detached OS background worker (`python -m tether.cli _worker <session_id>`)."""
    env = dict(os.environ)
    env["TETHER_DB"] = str(db_path)
    proc = subprocess.Popen(
        [sys.executable, "-m", "tether.cli", "_worker", session_id, "--db", str(db_path)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        env=env,
    )
    return proc.pid


class Harness:
    """General-purpose LLM-Native Micro-Harness."""

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
        max_context_tokens: int = 8192,
        fold_observations_after: int = 2,
        provider: ModelProvider | None = None,
        skill_search_dirs: list[str | Path] | None = None,
        worker_spawner: Callable[[str], int | None] | None = None,
    ) -> None:
        self.model = model or os.environ.get("TETHER_MODEL") or "ollama/qwen3.5:9b"
        self.store = SQLiteStore(db_path=db_path)
        self.sandbox = sandbox or SandboxPolicy()
        self.max_steps = max_steps
        self.max_verify_failures = max_verify_failures
        self.max_context_tokens = max_context_tokens
        self.fold_observations_after = fold_observations_after
        self._provider = provider
        self.skill_loader = SkillLoader(search_dirs=skill_search_dirs)
        self._worker_spawner = worker_spawner

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
                mux.register(make_web_tool())
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

    def create_session(self, goal: str, *, parent_id: str | None = None) -> SessionRecord:
        """Create a persisted session row in SQLite without executing it yet."""
        return self.store.create_session(
            goal=goal,
            model=self.model,
            skill=self.skill_name,
            tools=self._enabled_tool_names,
            sandbox_config=self.sandbox.to_dict(),
            parent_id=parent_id,
            max_steps=self.max_steps,
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
        """Send a message to a session's SQLite inbox; auto-resumes if COMPLETED/FAILED."""
        rec = self.store.get_session(session_id)
        if not rec:
            raise ValueError(f"Session `{session_id}` not found.")

        self.store.enqueue_inbox(session_id, message)
        if rec.status == "RUNNING":
            return rec

        # Session was IDLE/COMPLETED/FAILED -> resume it
        if headless:
            self.store.update_session(session_id, status="PENDING")
            spawner = self._spawner_for_store()
            spawner(session_id)
            updated = self.store.get_session(session_id)
            assert updated is not None
            return updated

        return await self.execute_session(session_id)

    async def _run_verification_gates(
        self,
        sandbox: SandboxPolicy,
        verify_commands: list[str],
        max_gate_output_chars: int = 2000,
    ) -> tuple[str, int, str] | None:
        """Run deterministic verification gates in order; return (cmd, code, output) on failure."""
        for vcmd in verify_commands:
            try:
                code, out = await sandbox.execute_bash_with_code(vcmd)
            except Exception as exc:
                code, out = 1, str(exc)

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
                return vcmd, code, compact_out
        return None

    async def execute_session(self, session_id: str) -> SessionRecord:
        """Execute the bounded agent loop for a persisted session in SQLite."""
        rec = self.store.get_session(session_id)
        if not rec:
            raise ValueError(f"Session `{session_id}` not found.")

        sandbox = SandboxPolicy.from_dict(rec.sandbox_config)
        skill_obj = self._skill
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
            *self._verify_commands,
        ]:
            if sv not in verify_commands:
                verify_commands.append(sv)

        mux = self.build_multiplexer(
            session_id=session_id,
            enabled_tools=enabled_tools,
            sandbox=sandbox,
            model=rec.model,
        )

        provider = self._provider or resolve_provider(rec.model, num_ctx=self.max_context_tokens)
        assembler = ContextAssembler(
            fold_after_turns=self.fold_observations_after,
            max_context_tokens=self.max_context_tokens,
        )
        system_prompt = assembler.build_system_prompt(
            toolbox_index=mux.toolbox_index(),
            skill_instructions=skill_obj.instructions if skill_obj else None,
        )

        self.store.update_session(session_id, status="RUNNING", pid=os.getpid())

        step_start = rec.step_count
        step_limit = step_start + rec.max_steps
        last_action_sig: tuple[str, str | None] | None = None
        consecutive_verify_failures = 0

        try:
            for step in range(step_start + 1, step_limit + 1):
                # 1. Poll SQLite inbox before each reasoning step
                inbox_msgs = self.store.consume_inbox(session_id)
                if inbox_msgs:
                    last_action_sig = None
                for imsg in inbox_msgs:
                    self.store.add_turn(
                        session_id=session_id,
                        step=step,
                        role="user",
                        content=f"[Follow-up instruction]: {imsg}",
                    )

                # 2. Assemble context with ephemeral observation folding
                turns = self.store.get_turns(session_id)
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
                resp = await provider.generate(messages, [ACT_TOOL_SCHEMA])
                actual_tokens = max(est_tokens, resp.prompt_tokens)
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
                )

                # 3. If the model emitted plain text without calling `act`, nudge it (Rule 3)
                if resp.action is None:
                    self.store.add_turn(
                        session_id=session_id,
                        step=step,
                        role="assistant",
                        content=resp.content or "(no output)",
                    )
                    self.store.add_turn(
                        session_id=session_id,
                        step=step,
                        role="user",
                        content=(
                            "System reminder: Use `act(cmd, stdin)` to execute a tool command, "
                            'or call `act("done", stdin="<final deliverable>")` to finish.'
                        ),
                    )
                    continue

                cmd = resp.action.cmd
                stdin = resp.action.stdin
                self.store.add_turn(
                    session_id=session_id,
                    step=step,
                    role="assistant",
                    content=resp.content,
                    tool_cmd=cmd,
                    tool_stdin=stdin,
                )

                action_sig = (cmd.strip(), stdin)
                if action_sig == last_action_sig and not cmd.strip().startswith("done"):
                    stall_msg = (
                        f"[LOOP DETECTED] You just ran `{cmd.strip()}` with identical input in the "
                        "previous step. Do not repeat the same command—inspect the prior output, "
                        'adjust your arguments, or call `act("done", stdin="...")` to finish.'
                    )
                    self.store.add_turn(
                        session_id=session_id,
                        step=step,
                        role="tool",
                        content=stall_msg,
                    )
                    continue
                last_action_sig = action_sig

                dispatch = await mux.execute(cmd, stdin=stdin)
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
                    if verify_commands:
                        gate_failure = await self._run_verification_gates(sandbox, verify_commands)
                        if gate_failure is not None:
                            failed_cmd, exit_code, gate_out = gate_failure
                            consecutive_verify_failures += 1
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

                    final_text = dispatch.final_result or ""
                    self.store.add_turn(
                        session_id=session_id,
                        step=step,
                        role="tool",
                        content=f"[COMPLETED] {final_text}",
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

                # Record tool observation in SQLite (auto-chunks into FTS5)
                obs = self.store.add_observation(
                    session_id=session_id,
                    step=step,
                    cmd=cmd,
                    raw_output=dispatch.output,
                )
                self.store.add_turn(
                    session_id=session_id,
                    step=step,
                    role="tool",
                    content=dispatch.output,
                    obs_id=obs.id,
                )

            # Max steps reached without explicit `done`
            self.store.update_session(
                session_id,
                status="FAILED",
                result=f"Max steps ({rec.max_steps}) reached without calling `done`.",
            )
        except Exception as exc:
            self.store.update_session(
                session_id,
                status="FAILED",
                result=f"Worker error: {exc}",
            )

        final_rec = self.store.get_session(session_id)
        assert final_rec is not None
        return final_rec
