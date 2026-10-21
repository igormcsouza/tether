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


def test_bare_shell_command_is_redirected_to_bash(tether: Tether, chaos) -> None:
    chaos.script("ls", ("done", "ok"))
    r = tether.run("list", "--tools", "bash")
    assert "For shell commands use `bash ls`" in tether.tool_outputs(r["id"])[0]
    assert tether.events(r["id"])[0] == "syntax_error"


def test_prompt_and_backtick_wrappers_are_normalised(tether: Tether, chaos) -> None:
    chaos.script("$ bash echo hi", "`bash echo hi`", ("done", "ok"))
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


def test_identical_repeat_is_a_loop_stall(tether: Tether, chaos) -> None:
    chaos.script("bash true", "bash true", ("done", "ok"))
    r = tether.run("loop", "--tools", "bash")
    assert tether.events(r["id"]) == ["ok", "loop_stall", "completed"]
    assert "[LOOP DETECTED]" in _last_prompt(chaos)


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
