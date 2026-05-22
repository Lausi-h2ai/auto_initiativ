from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlmodel import Session, select

from backend.app.core.config import Settings, get_settings
from backend.app.db.models import AuditLog, Run, utc_now


@dataclass(frozen=True)
class ExecCommandResult:
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class CodexExecRequest:
    run_id: str
    run_dir: Path
    prompt: str
    output_path: Path | None = None
    output_schema_path: Path | None = None
    sandbox: str | None = None
    timeout_seconds: float | None = None
    codex_binary: str | None = None
    json_events: bool | None = None
    ephemeral: bool = True


@dataclass(frozen=True)
class CodexExecResult:
    run_id: str
    status: str
    command: list[str]
    exit_code: int | None
    stdout: str
    stderr: str
    started_at: str
    completed_at: str
    duration_seconds: float
    failure_reason: str | None
    log_path: Path

    def metadata(self) -> dict[str, Any]:
        data = asdict(self)
        data["log_path"] = str(self.log_path)
        return data


Runner = Callable[[Sequence[str], Path, float | None, Mapping[str, str]], ExecCommandResult]


def _json_dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_runner(args: Sequence[str], cwd: Path, timeout: float | None, env: Mapping[str, str]) -> ExecCommandResult:
    result = subprocess.run(
        list(args),
        cwd=cwd,
        env=dict(env),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return ExecCommandResult(returncode=result.returncode, stdout=result.stdout, stderr=result.stderr)


class CodexExecAdapter:
    """Run non-interactive Codex tasks and persist execution logs.

    Stdout and stderr are execution evidence only. Importable agent output must
    still be written under the run's output directory and validated separately.
    """

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        runner: Runner = _default_runner,
        session: Session | None = None,
        env: Mapping[str, str] | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.runner = runner
        self.session = session
        self.env = env

    def run(self, request: CodexExecRequest) -> CodexExecResult:
        run_dir = request.run_dir
        logs_dir = run_dir / "logs"
        output_dir = run_dir / "output"
        logs_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)

        command = self.build_command(request)
        logged_command = self._logged_command(command)
        timeout = request.timeout_seconds if request.timeout_seconds is not None else self.settings.codex_exec_timeout_seconds

        started_at = _utc_now_iso()
        start_monotonic = time.monotonic()
        self._mark_started(request.run_id, output_dir, logged_command, started_at)

        exit_code: int | None
        stdout = ""
        stderr = ""
        status: str
        failure_reason: str | None

        try:
            command_result = self.runner(command, run_dir, timeout, self._safe_env())
            exit_code = command_result.returncode
            stdout = command_result.stdout
            stderr = command_result.stderr
            if command_result.returncode == 0:
                status = "succeeded"
                failure_reason = None
            else:
                status = "failed"
                failure_reason = "nonzero_exit"
        except subprocess.TimeoutExpired as exc:
            exit_code = None
            stdout = _decode_timeout_output(exc.stdout)
            stderr = _decode_timeout_output(exc.stderr)
            status = "timed_out"
            failure_reason = "timeout"
        except FileNotFoundError as exc:
            exit_code = None
            stderr = str(exc)
            status = "missing_executable"
            failure_reason = "missing_executable"

        completed_at = _utc_now_iso()
        duration_seconds = round(time.monotonic() - start_monotonic, 6)
        result = CodexExecResult(
            run_id=request.run_id,
            status=status,
            command=logged_command,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=duration_seconds,
            failure_reason=failure_reason,
            log_path=logs_dir / "codex_exec.json",
        )
        self._write_logs(result, logs_dir)
        self._mark_completed(result, output_dir)
        return result

    def build_command(self, request: CodexExecRequest) -> list[str]:
        sandbox = request.sandbox if request.sandbox is not None else self.settings.codex_exec_sandbox
        codex_binary = request.codex_binary or self.settings.codex_exec_binary
        json_events = request.json_events if request.json_events is not None else self.settings.codex_exec_json_events

        command = [codex_binary, "exec"]
        if request.ephemeral:
            command.append("--ephemeral")
        if json_events:
            command.append("--json")
        command.extend(["--sandbox", sandbox])
        if request.output_schema_path is not None:
            command.extend(["--output-schema", str(request.output_schema_path)])
        if request.output_path is not None:
            command.extend(["-o", str(request.output_path)])
        command.append(request.prompt)
        return command

    def _safe_env(self) -> Mapping[str, str]:
        if self.env is not None:
            return self.env
        allowed_names = {
            "APPDATA",
            "COMSPEC",
            "HOME",
            "LOCALAPPDATA",
            "PATH",
            "PATHEXT",
            "PROGRAMDATA",
            "SYSTEMDRIVE",
            "SYSTEMROOT",
            "TEMP",
            "TMP",
            "USERPROFILE",
            "WINDIR",
        }
        return {key: value for key, value in os.environ.items() if key.upper() in allowed_names}

    def _logged_command(self, command: Sequence[str]) -> list[str]:
        if not command:
            return []
        return [*command[:-1], self._prompt_fingerprint(command[-1])]

    @staticmethod
    def _prompt_fingerprint(prompt: str) -> str:
        digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        return f"<prompt sha256={digest} length={len(prompt)}>"

    def _write_logs(self, result: CodexExecResult, logs_dir: Path) -> None:
        payload = result.metadata()
        result.log_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        with (logs_dir / "codex_exec.jsonl").open("a", encoding="utf-8") as file:
            file.write(_json_dumps(payload) + "\n")

    def _mark_started(self, run_id: str, output_dir: Path, command: list[str], started_at: str) -> None:
        if self.session is None:
            return
        run = self._get_or_create_run(run_id, output_dir)
        run.agent_type = "codex_exec"
        run.status = "codex_exec_running"
        run.started_at = datetime.fromisoformat(started_at)
        run.completed_at = None
        run.updated_at = utc_now()
        self.session.add(run)
        self._audit(
            run_id=run_id,
            action="codex_exec_started",
            result_status="started",
            metadata={"command": command, "output_path": str(output_dir)},
        )
        self.session.commit()

    def _mark_completed(self, result: CodexExecResult, output_dir: Path) -> None:
        if self.session is None:
            return
        run = self._get_or_create_run(result.run_id, output_dir)
        run.agent_type = "codex_exec"
        run.status = f"codex_exec_{result.status}"
        run.completed_at = datetime.fromisoformat(result.completed_at)
        run.updated_at = utc_now()
        self.session.add(run)
        self._audit(
            run_id=result.run_id,
            action="codex_exec_completed",
            result_status=result.status,
            reason_codes=[result.failure_reason] if result.failure_reason else [],
            metadata={
                "command": result.command,
                "exit_code": result.exit_code,
                "duration_seconds": result.duration_seconds,
                "failure_reason": result.failure_reason,
                "log_path": str(result.log_path),
            },
        )
        self.session.commit()

    def _get_or_create_run(self, run_id: str, output_dir: Path) -> Run:
        run = self.session.exec(select(Run).where(Run.run_id == run_id)).first() if self.session is not None else None
        if run is None:
            run = Run(run_id=run_id, output_path=str(output_dir), status="created")
        else:
            run.output_path = str(output_dir)
        return run

    def _audit(
        self,
        *,
        run_id: str,
        action: str,
        result_status: str,
        reason_codes: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if self.session is None:
            return
        self.session.add(
            AuditLog(
                run_id=run_id,
                actor_type="backend",
                action=action,
                entity_type="run",
                entity_id=run_id,
                result_status=result_status,
                reason_codes_json=_json_dumps(reason_codes or []),
                metadata_json=_json_dumps(metadata or {}),
            )
        )


def _decode_timeout_output(value: bytes | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value
