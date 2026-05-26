from __future__ import annotations

import json
import subprocess
from pathlib import Path

from sqlmodel import select

from backend.app.agents.codex_exec import CodexExecAdapter, CodexExecRequest, ExecCommandResult
from backend.app.db.models import AuditLog, ImportedFile, Run


class FakeRunner:
    def __init__(self, result: ExecCommandResult | None = None, error: Exception | None = None) -> None:
        self.result = result or ExecCommandResult(returncode=0, stdout="", stderr="")
        self.error = error
        self.calls: list[tuple[list[str], Path, float | None, dict[str, str]]] = []

    def __call__(self, args, cwd, timeout, env):
        self.calls.append((list(args), cwd, timeout, dict(env)))
        if self.error is not None:
            raise self.error
        return self.result


def test_codex_exec_adapter_builds_command_runs_in_run_folder_and_writes_logs(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-be-forwarded")
    runner = FakeRunner(ExecCommandResult(returncode=0, stdout='{"event":"done"}\n', stderr="diagnostic\n"))
    run_dir = tmp_path / "runs" / "exec-success"
    request = CodexExecRequest(
        run_id="exec-success",
        run_dir=run_dir,
        prompt="Write output files only under output/.",
        output_path=run_dir / "logs" / "final.txt",
        output_schema_path=tmp_path / "schema.json",
        timeout_seconds=12,
    )

    result = CodexExecAdapter(runner=runner).run(request)

    assert result.status == "succeeded"
    assert result.exit_code == 0
    assert result.stdout == '{"event":"done"}\n'
    assert runner.calls[0][1] == run_dir
    assert runner.calls[0][2] == 12
    assert runner.calls[0][0][0:5] == ["codex", "exec", "--ephemeral", "--json", "--sandbox"]
    assert "--output-schema" in runner.calls[0][0]
    assert "-o" in runner.calls[0][0]
    assert "OPENAI_API_KEY" not in runner.calls[0][3]

    log_payload = json.loads((run_dir / "logs" / "codex_exec.json").read_text(encoding="utf-8"))
    assert log_payload["status"] == "succeeded"
    assert log_payload["stdout"] == '{"event":"done"}\n'
    assert log_payload["stderr"] == "diagnostic\n"
    assert log_payload["command"][-1].startswith("<prompt sha256=")
    assert (run_dir / "logs" / "codex_exec.jsonl").read_text(encoding="utf-8").strip()


def test_codex_exec_adapter_persists_run_and_audit_for_success(db_session, tmp_path):
    runner = FakeRunner(ExecCommandResult(returncode=0, stdout="ok", stderr=""))
    run_dir = tmp_path / "runs" / "exec-audit"

    result = CodexExecAdapter(runner=runner, session=db_session).run(
        CodexExecRequest(run_id="exec-audit", run_dir=run_dir, prompt="Do the task.")
    )

    assert result.status == "succeeded"
    run = db_session.exec(select(Run).where(Run.run_id == "exec-audit")).one()
    assert run.status == "codex_exec_succeeded"
    assert run.agent_type == "codex_exec"

    audits = db_session.exec(select(AuditLog).where(AuditLog.run_id == "exec-audit").order_by(AuditLog.action)).all()
    assert [audit.action for audit in audits] == ["codex_exec_completed", "codex_exec_started"]
    completed = next(audit for audit in audits if audit.action == "codex_exec_completed")
    assert completed.result_status == "succeeded"
    assert json.loads(completed.metadata_json)["log_path"].endswith("codex_exec.json")


def test_codex_exec_adapter_records_nonzero_exit_without_importing_stdout(db_session, tmp_path):
    runner = FakeRunner(ExecCommandResult(returncode=2, stdout='{"filename":"send_intent.json"}', stderr="bad prompt"))
    run_dir = tmp_path / "runs" / "exec-failed"

    result = CodexExecAdapter(runner=runner, session=db_session).run(
        CodexExecRequest(run_id="exec-failed", run_dir=run_dir, prompt="Do the task.")
    )

    assert result.status == "failed"
    assert result.failure_reason == "nonzero_exit"
    run = db_session.exec(select(Run).where(Run.run_id == "exec-failed")).one()
    assert run.status == "codex_exec_failed"
    assert db_session.exec(select(ImportedFile)).all() == []
    completed = db_session.exec(select(AuditLog).where(AuditLog.action == "codex_exec_completed")).one()
    assert json.loads(completed.reason_codes_json) == ["nonzero_exit"]


def test_codex_exec_adapter_records_timeout(tmp_path):
    timeout = subprocess.TimeoutExpired(cmd=["codex"], timeout=3, output=b"partial", stderr=b"still running")
    runner = FakeRunner(error=timeout)

    result = CodexExecAdapter(runner=runner).run(
        CodexExecRequest(run_id="exec-timeout", run_dir=tmp_path / "runs" / "exec-timeout", prompt="Do the task.", timeout_seconds=3)
    )

    assert result.status == "timed_out"
    assert result.failure_reason == "timeout"
    assert result.exit_code is None
    assert result.stdout == "partial"
    assert result.stderr == "still running"


def test_codex_exec_adapter_records_missing_executable(tmp_path):
    runner = FakeRunner(error=FileNotFoundError("codex"))

    result = CodexExecAdapter(runner=runner).run(
        CodexExecRequest(run_id="exec-missing", run_dir=tmp_path / "runs" / "exec-missing", prompt="Do the task.")
    )

    assert result.status == "missing_executable"
    assert result.failure_reason == "missing_executable"
    assert result.exit_code is None
    assert "codex" in result.stderr


def test_codex_exec_adapter_allows_fake_runner_environment_override(tmp_path):
    runner = FakeRunner()

    CodexExecAdapter(runner=runner, env={"PATH": "fake-path"}).run(
        CodexExecRequest(run_id="exec-env", run_dir=tmp_path / "runs" / "exec-env", prompt="Do the task.")
    )

    assert runner.calls[0][3] == {"PATH": "fake-path"}
