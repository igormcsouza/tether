"""Session lifecycle, exit codes, resume. Scripted: the proxy plays the model, tether is real."""

from __future__ import annotations

from e2e.conftest import Tether


def test_done_completes_with_exit_0(tether: Tether, chaos) -> None:
    chaos.script(("done", "all good"))
    r = tether.run("finish")
    assert (r["rc"], r["status"], r["result"]) == (0, "COMPLETED", "all good")


def test_done_ask_pauses_with_exit_2_and_send_resumes(tether: Tether, chaos) -> None:
    chaos.script(("done --ask", "Which name: alpha or beta?"))
    r = tether.run("pick a name")
    assert (r["rc"], r["status"], r["result"]) == (2, "WAITING_INPUT", "Which name: alpha or beta?")
    chaos.requests.clear()
    chaos.script(("done", "named it beta"))
    r2 = tether.send(r["id"], "beta")
    assert (r2["rc"], r2["status"], r2["result"]) == (0, "COMPLETED", "named it beta")
    assert "beta" in str(chaos.requests[0]["messages"]), "the human's reply must reach the model"


def test_max_steps_exit_4_and_resume_never_exceeds_ceiling(tether: Tether, chaos) -> None:
    chaos.script(*[("bash true",)] * 20)  # never calls done
    r = tether.run("never finishes", "--tools", "bash", "--max-steps", "3")
    assert (r["rc"], r["status"], r["steps"], r["max_steps"]) == (4, "FAILED", 3, 3)
    r2 = tether.send(r["id"], "go on")  # #75: resume extends the ceiling, never overshoots it
    assert r2["steps"] > 3 and r2["steps"] <= r2["max_steps"], r2


def test_gate_failure_exit_3_with_circuit_breaker(tether: Tether, chaos) -> None:
    chaos.script(*[("done", "x")] * 10)
    r = tether.run("gate", "--verify", "false")
    assert (r["rc"], r["status"]) == (3, "FAILED") and r["failure"]["kind"] == "gate"
    assert tether.events(r["id"]).count("gate_fail") == 3  # max_verify_failures


def test_broken_gate_fails_at_once_as_gate_error(tether: Tether, chaos) -> None:
    chaos.script(("done", "x"))
    r = tether.run("gate", "--verify", "exit 127")
    assert (r["rc"], r["status"]) == (3, "FAILED") and r["steps"] == 1
    assert "gate_error" in tether.events(r["id"]) and "misconfigured" in str(r["failure"])


def test_passing_gate_lets_done_complete(tether: Tether, chaos) -> None:
    chaos.script(("done", "ok"))
    r = tether.run("gate", "--verify", "true")
    assert (r["rc"], r["status"]) == (0, "COMPLETED")


def test_output_schema_rejects_then_accepts(tether: Tether, chaos) -> None:
    (tether.ws / "schema.json").write_text('{"type":"object","required":["a"]}')
    chaos.script(("done", "not json"), ("done", '{"a": 1}'))
    r = tether.run("schema", "--output-schema", "schema.json")
    assert (r["rc"], r["status"]) == (0, "COMPLETED") and r["result"] == '{"a": 1}'
    assert tether.events(r["id"]).count("gate_fail") == 1


def test_headless_run_wait_read_status(tether: Tether, chaos) -> None:
    chaos.script(("done", "headless result"))
    p = tether.cli("run", "--headless", "--model", "e2e/scripted", "go")
    sid = p.stdout.strip()
    assert p.returncode == 0 and sid.startswith("ses_")
    assert tether.cli("wait", sid).returncode == 0
    assert tether.cli("read", sid).stdout.strip() == "headless result"
    assert "COMPLETED" in tether.cli("status", sid).stdout
