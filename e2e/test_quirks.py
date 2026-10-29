"""Small-model quirks and context behaviour. Scripted replies reproduce what real models did;
tether must normalise or self-heal deterministically (Rules 3, 5, 5.3)."""

from __future__ import annotations

from e2e.conftest import Tether


def _last_prompt(chaos) -> str:
    return "\n".join(str(m.get("content", "")) for m in chaos.requests[-1]["messages"])


def test_heredoc_in_cmd_becomes_stdin(tether: Tether, chaos) -> None:
    chaos.script("edit write a.txt <<'EOF'\nhello\nEOF", ("done", "ok"))
    tether.run("heredoc", "--tools", "edit")
    assert (tether.ws / "a.txt").read_text() == "hello"


def test_bare_shell_command_runs_through_bash(tether: Tether, chaos) -> None:
    (tether.ws / "marker.txt").write_text("x")
    chaos.script("ls", ("done", "ok"))
    r = tether.run("list", "--tools", "bash")
    assert "marker.txt" in tether.tool_outputs(r["id"])[0]
    assert tether.events(r["id"])[0] == "ok"


def test_shell_wrapper_is_unwrapped(tether: Tether, chaos) -> None:
    (tether.ws / "marker.txt").write_text("x")
    chaos.script("bash -lc 'ls'", ("done", "ok"))
    r = tether.run("wrapper", "--tools", "bash")
    assert "marker.txt" in tether.tool_outputs(r["id"])[0]
    assert tether.events(r["id"])[0] == "ok"


def test_apply_patch_edits_a_file(tether: Tether, chaos) -> None:
    (tether.ws / "p.txt").write_text("one\n")
    patch = "*** Begin Patch\n*** Update File: p.txt\n-one\n+two\n*** End Patch"
    chaos.script(("apply_patch", patch), ("done", "ok"))
    tether.run("patch", "--tools", "edit")
    assert (tether.ws / "p.txt").read_text() == "two\n"


def test_unified_diff_in_stdin_patches_instead_of_overwriting(tether: Tether, chaos) -> None:
    (tether.ws / "p.py").write_text("a = 1\nb = 2\nc = 3\n")
    diff = "--- p.py\n+++ p.py\n@@ -1,3 +1,3 @@\n a = 1\n-b = 2\n+b = 20\n c = 3\n"
    chaos.script(("edit p.py", diff), ("done", "ok"))  # verbless edit + diff, as gemma4 sends it
    tether.run("diff", "--tools", "edit")
    assert (tether.ws / "p.py").read_text() == "a = 1\nb = 20\nc = 3\n"


def test_prompt_and_backtick_wrappers_are_normalised(tether: Tether, chaos) -> None:
    chaos.script("$ bash echo hi", "`bash echo bye`", ("done", "ok"))
    r = tether.run("quirks", "--tools", "bash")
    assert tether.events(r["id"])[:2] == ["ok", "ok"]


def test_literal_backslash_n_in_one_line_stdin_is_unescaped(tether: Tether, chaos) -> None:
    chaos.script(("edit write a.txt", "one\\ntwo"), ("done", "ok"))
    tether.run("write", "--tools", "edit")
    assert (tether.ws / "a.txt").read_text() == "one\ntwo"


def test_plain_text_reply_gets_a_nudge_not_a_completion(tether: Tether, chaos) -> None:
    chaos.script({"text": "I will think about it."}, ("done", "ok"))
    r = tether.run("nudge")
    assert tether.events(r["id"]) == ["nudge", "completed"] and r["status"] == "COMPLETED"
    assert "done" in tether.tool_outputs(r["id"])[0].lower() or "done" in _last_prompt(chaos)


def test_named_json_tool_call_in_text_is_understood(tether: Tether, chaos) -> None:
    """qwen2.5-coder writes {"name": "edit", "arguments": {...}} as text, not a tool call."""
    reply = '{"name": "edit", "arguments": {"file": "a.txt", "mode": "view"}}'
    chaos.script({"text": reply}, ("done", "ok"))
    r = tether.run("view", "--tools", "edit")
    assert tether.events(r["id"])[0] != "nudge" and r["status"] == "COMPLETED"
    assert "a.txt" in tether.tool_outputs(r["id"])[0]  # it ran `edit view a.txt`


def test_edit_call_written_with_file_and_content_writes_the_file(tether: Tether, chaos) -> None:
    reply = '{"name": "edit", "arguments": {"file": "a.txt", "content": "one\\ntwo"}}'
    chaos.script({"text": reply}, ("done", "ok"))
    r = tether.run("write", "--tools", "edit")
    assert r["status"] == "COMPLETED" and (tether.ws / "a.txt").read_text().startswith("one\ntwo")


def test_identical_repeat_is_a_loop_stall(tether: Tether, chaos) -> None:
    chaos.script("bash true", "bash true", ("done", "ok"))
    r = tether.run("loop", "--tools", "bash")
    assert tether.events(r["id"]) == ["ok", "loop_stall", "completed"]
    assert "[LOOP DETECTED]" in _last_prompt(chaos)


def test_stall_after_a_change_with_a_passing_gate_is_completed(tether: Tether, chaos) -> None:
    chaos.script(*(["bash touch fixed.txt"] * 6), ("done", "ok"))  # #163: fixed, then only repeats
    r = tether.run("loop", "--tools", "bash", "--verify", "test -f fixed.txt")
    assert r["status"] == "COMPLETED" and "Finished by the harness" in r["result"]


def test_stall_with_a_failing_gate_stays_failed(tether: Tether, chaos) -> None:
    chaos.script(*(["bash touch fixed.txt"] * 6), ("done", "ok"))
    r = tether.run("loop", "--tools", "bash", "--verify", "test -f missing.txt")
    assert r["status"] == "FAILED" and r["failure"]["message"].startswith("Stalled")


def test_unfinished_session_reports_changes_and_gate(tether: Tether, chaos) -> None:
    chaos.script(*(["bash touch fixed.txt"] * 6), ("done", "ok"))  # #171: never a bare error
    r = tether.run("loop", "--tools", "bash", "--verify", "test -f missing.txt")
    msg = r["failure"]["message"]
    assert "Changed: `bash touch fixed.txt`" in msg and "Gate `test -f missing.txt` fails" in msg


def test_never_calling_done_after_a_green_test_run_is_completed(tether: Tether, chaos) -> None:
    (tether.ws / "test_ok.py").write_text(
        "import unittest\n\n\nclass T(unittest.TestCase):\n    def test_ok(self):\n        pass\n"
    )
    cmds = ("bash touch fixed.txt", "bash python3 -m unittest test_ok", "bash ls", "bash ls -a")
    chaos.script(*cmds)
    r = tether.run("never done", "--tools", "bash", "--max-steps", "4")  # #177
    assert r["status"] == "COMPLETED" and "Finished by the harness" in r["result"]
    assert "[NUDGE] Tests pass after your last change" in "\n".join(tether.tool_outputs(r["id"]))


def test_read_only_stall_is_asked_for_its_answer_once(tether: Tether, chaos) -> None:
    chaos.script(*(["bash ls"] * 5), ("done", "my review"))  # #wrap-up: answer from what you read
    r = tether.run("review", "--tools", "bash")
    assert r["status"] == "COMPLETED" and r["result"] == "my review"
    assert "[WRAP UP]" in "\n".join(tether.tool_outputs(r["id"]))


def test_two_command_cycle_is_a_cycle_stall(tether: Tether, chaos) -> None:
    chaos.script(*(["bash echo a", "bash echo b"] * 3), ("done", "ok"))
    r = tether.run("cycle", "--tools", "bash")
    assert "cycle_stall" in tether.events(r["id"]) and "[CYCLE DETECTED]" in _last_prompt(chaos)


def test_lost_indentation_is_flagged_immediately(tether: Tether, chaos) -> None:
    (tether.ws / "c.py").write_text("def f():\n    for x in [1]:\n        print(x)\n")
    chaos.script(("edit replace c.py --lines 3:3", "print(x)"), ("done", "ok"))
    r = tether.run("edit", "--tools", "edit")
    assert "WARNING: `c.py` no longer parses" in tether.tool_outputs(r["id"])[0]


def test_search_replace_block_tolerates_missing_final_marker(tether: Tether, chaos) -> None:
    (tether.ws / "a.txt").write_text("alpha\nbeta\n")
    chaos.script(("edit replace a.txt", "<<<<<<< SEARCH\nbeta\n=======\nBETA"), ("done", "ok"))
    tether.run("edit", "--tools", "edit")
    assert (tether.ws / "a.txt").read_text() == "alpha\nBETA\n"


def test_quiet_stretch_after_a_change_gets_one_done_nudge(tether: Tether, chaos) -> None:
    chaos.script(
        ("edit write a.txt", "x\n"),
        *[f"edit view a.txt --lines 1:{i}" for i in range(1, 9)],
        ("done", "ok"),
    )
    r = tether.run("nudge me", "--tools", "edit", "--max-steps", "12")
    nudged = [o for o in tether.tool_outputs(r["id"]) if "[NUDGE]" in o]
    assert len(nudged) == 1 and r["status"] == "COMPLETED"


def test_old_observations_fold_to_a_recallable_tombstone(tether: Tether, chaos) -> None:
    big = "python3 -c \"print('x'*3000)\""
    chaos.script(f"bash {big}", "bash echo 1", "bash echo 2", "bash echo 3", ("done", "ok"))
    tether.run("fold", "--tools", "bash,mem", "--max-steps", "8")
    prompt = _last_prompt(chaos)
    assert "[obs_1 folded" in prompt and "mem recall obs_1" in prompt


def test_two_ranges_of_one_file_stay_visible_together(tether: Tether, chaos) -> None:
    (tether.ws / "big.py").write_text(
        "".join(f"def function_number_{i}():\n    return 'value {i} padded'\n\n" for i in range(80))
    )
    chaos.script(
        "edit view big.py --lines 1:40",
        "edit view big.py --lines 41:80",
        "edit view big.py --lines 1:40",
        "edit view big.py --lines 41:80",
        "edit view big.py --lines 1:40",
        ("done", "ok"),
    )
    tether.run("read", "--tools", "edit", "--max-steps", "8")
    prompt = _last_prompt(chaos)
    # #99: the latest read of EACH range stays unfolded; the older repeats fold
    assert "[obs_4 folded" not in prompt and "[obs_5 folded" not in prompt
    assert "[obs_1 folded" in prompt and "[obs_3 folded" in prompt


def test_mem_pins_survive_and_search_finds_them(tether: Tether, chaos) -> None:
    chaos.script("mem pin colour teal", "mem search teal", ("done", "ok"))
    r = tether.run("remember", "--tools", "mem")
    assert "teal" in tether.tool_outputs(r["id"])[1]


def test_skill_enables_its_tools_without_touching_the_schema(tether: Tether, chaos) -> None:
    sk = tether.ws / "skills" / "tidy"
    sk.mkdir(parents=True)
    (sk / "SKILL.md").write_text(
        "---\nname: tidy\ndescription: tidy up\ntools: [bash]\n---\nAlways run `bash true` first.\n"
    )
    chaos.script(("done", "ok"))
    tether.run("tidy", "--skill", "tidy")
    req = chaos.requests[0]
    sysmsg = req["messages"][0]["content"]
    assert [t["function"]["name"] for t in req["tools"]] == ["act"]
    assert "- bash:" in sysmsg and "[SKILL]" in sysmsg and "Always run `bash true` first." in sysmsg


def test_bare_done_completes_instead_of_looping(tether: Tether, chaos) -> None:
    chaos.script("done")  # #169: was "Error: provide final deliverable", repeated to max_steps
    r = tether.run("finish", "--tools", "bash")
    assert r["status"] == "COMPLETED"
    assert tether.events(r["id"]) == ["completed"]


def test_act_call_typed_as_text_is_unwrapped(tether: Tether, chaos) -> None:
    chaos.script('act("done", stdin="all green")')
    r = tether.run("finish", "--tools", "bash")
    assert r["status"] == "COMPLETED" and r["result"] == "all green"
