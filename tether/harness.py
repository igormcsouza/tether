"""Control Plane: Tether Harness, bounded agent loop, live SQLite inbox, and headless spawner."""

from __future__ import annotations

import os
import subprocess
import sys
import time
import traceback
from collections.abc import Callable
from pathlib import Path
from typing import Any

from tether.context import ACT_TOOL_SCHEMA, ContextAssembler, estimate_messages_tokens
from tether.decorator import ToolSpec, build_tool_spec
from tether.multiplexer import Multiplexer
from tether.pipeline import Pipeline, load_pipeline, parse_pipeline_yaml, render_stage_goal
from tether.providers import ModelProvider, resolve_provider
from tether.providers.declarative import load_declared
from tether.sandbox import SandboxPolicy
from tether.schema import validate_output
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


def detect_cycle(history: list[tuple[str, str | None]], window: int = 8) -> list[str] | None:
    """Repeated n-gram (n=2..3) at the tail of the last `window` actions, else None.

    Identical-command runs are `loop_stall`'s job, so they are not a cycle here.
    """
    recent = history[-window:]
    for n in (2, 3):
        if (
            len(recent) >= 2 * n
            and recent[-n:] == recent[-2 * n : -n]
            and len(set(recent[-n:])) > 1
        ):
            return [cmd for cmd, _ in recent[-n:]]
    return None


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
    """General-purpose LLM-Native Micro-Harness.

    `output_schema` (JSON Schema subset) is a deterministic pre-`done` gate: the deliverable
    must be JSON matching it. `tether.api.failure_info` classifies FAILED results by the
    prefixes "Verification gate", "Max steps" and "Worker error" written in this module.
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
        max_context_tokens: int | None = None,
        fold_observations_after: int | None = None,
        provider: ModelProvider | None = None,
        skill_search_dirs: list[str | Path] | None = None,
        worker_spawner: Callable[[str], int | None] | None = None,
        output_schema: dict[str, Any] | None = None,
    ) -> None:
        self.model = model or os.environ.get("TETHER_MODEL") or "ollama/qwen3.5:9b"
        self.store = SQLiteStore(db_path=db_path)
        self.sandbox = sandbox or SandboxPolicy()
        self.max_steps = max_steps
        self.max_verify_failures = max_verify_failures
        declared: dict[str, Any] = {}
        try:
            declared = load_declared().get(self.model.split("/")[0], {})
        except ValueError:
            declared = {}
        self.max_context_tokens: int = int(
            max_context_tokens or declared.get("context_tokens") or 8192
        )
        self.fold_observations_after: int = int(
            fold_observations_after or declared.get("fold_after") or 2
        )
        self._provider = provider
        self.skill_loader = SkillLoader(search_dirs=skill_search_dirs)
        self._worker_spawner = worker_spawner
        self.output_schema = output_schema

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
        sbox_dict = root_sandbox.to_dict()
        sbox_dict["pipeline"] = resolved.to_dict()
        return self.store.create_session(
            goal=goal,
            model=self.model,
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

    def create_session(self, goal: str, *, parent_id: str | None = None) -> SessionRecord:
        """Create a persisted session row in SQLite without executing it yet."""
        sbox_dict = self.sandbox.to_dict()
        if self.output_schema:
            sbox_dict["output_schema"] = self.output_schema
        return self.store.create_session(
            goal=goal,
            model=self.model,
            skill=self.skill_name,
            tools=self._enabled_tool_names,
            sandbox_config=sbox_dict,
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
        """Send a message to SQLite inbox; auto-resumes if WAITING_INPUT/COMPLETED/FAILED."""
        rec = self.store.get_session(session_id)
        if not rec:
            raise ValueError(f"Session `{session_id}` not found.")

        self.store.enqueue_inbox(session_id, message)
        if rec.status == "RUNNING":
            return rec

        # Session was WAITING_INPUT/IDLE/COMPLETED/FAILED -> resume it
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

    async def _execute_pipeline_session(self, rec: SessionRecord) -> SessionRecord:
        """Execute a deterministic multi-stage pipeline with isolated child sessions."""
        raw_pipe = rec.sandbox_config.get("pipeline")
        assert isinstance(raw_pipe, dict)
        pipeline = Pipeline.from_dict(raw_pipe)
        root_sandbox = SandboxPolicy.from_dict(rec.sandbox_config)

        self.store.update_session(rec.id, status="RUNNING", pid=os.getpid())
        completed_stages: list[tuple[str, SessionRecord]] = []

        for idx, stage in enumerate(pipeline.stages, start=1):
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
                or rec.model
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

        output_schema = rec.sandbox_config.get("output_schema") or None

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
            structured=bool(getattr(provider, "structured_history", False)),
        )
        system_prompt = assembler.build_system_prompt(
            toolbox_index=mux.toolbox_index(),
            skill_instructions=skill_obj.instructions if skill_obj else None,
        )

        self.store.update_session(session_id, status="RUNNING", pid=os.getpid())

        step_start = rec.step_count
        step_limit = step_start + rec.max_steps
        last_action_sig: tuple[str, str | None] | None = None
        action_history: list[tuple[str, str | None]] = []
        consecutive_verify_failures = 0

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
                t_llm_start = time.perf_counter()
                resp = await provider.generate(messages, [ACT_TOOL_SCHEMA])
                llm_duration_ms = int((time.perf_counter() - t_llm_start) * 1000)

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
                if resp.action is None:
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
                        content=(
                            "System reminder: Use `act(cmd, stdin)` to execute a tool command, "
                            'or call `act("done", stdin="<final deliverable>")` to finish.'
                        ),
                    )
                    continue

                cmd = resp.action.cmd
                stdin = resp.action.stdin
                action_sig = (cmd.strip(), stdin)
                is_loop_stall = action_sig == last_action_sig and not cmd.strip().startswith("done")
                cycle = (
                    None
                    if is_loop_stall or cmd.strip().startswith("done")
                    else detect_cycle([*action_history, action_sig])
                )

                assistant_turn_id = self.store.add_turn(
                    session_id=session_id,
                    step=step,
                    role="assistant",
                    content=resp.content,
                    tool_cmd=cmd,
                    tool_stdin=stdin,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    duration_ms=llm_duration_ms,
                    event_type="loop_stall" if is_loop_stall else "cycle_stall" if cycle else "ok",
                )

                if is_loop_stall:
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
                if cycle:
                    action_history.clear()
                    cycle_msg = (
                        f"[CYCLE DETECTED] You are repeating the commands "
                        f"{' -> '.join(f'`{c}`' for c in cycle)} "
                        "and the output/file did not change. Stop: re-read the last output, "
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
                action_history.append(action_sig)

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
                            ("output-schema", 1, schema_err)
                            if schema_err
                            else await self._run_verification_gates(sandbox, verify_commands)
                        )
                        gate_duration_ms = int((time.perf_counter() - t_gate_start) * 1000)
                        if gate_failure is not None:
                            failed_cmd, exit_code, gate_out = gate_failure
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
                elif dispatch.is_error:
                    self.store.update_turn_telemetry(assistant_turn_id, event_type="tool_error")

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
                    duration_ms=tool_duration_ms,
                )

            # Max steps reached without explicit `done`
            self.store.update_session(
                session_id,
                status="FAILED",
                result=f"Max steps ({rec.max_steps}) reached without calling `done`.",
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
