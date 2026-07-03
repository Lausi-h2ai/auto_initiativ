from __future__ import annotations

import json
import os
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlmodel import Session, select

from backend.app.agents.company_research import COMPANY_RESEARCH_INSTRUCTIONS
from backend.app.agents.pi_rpc import ClientFactory, PiRpcClient, PiRpcClientProtocol
from backend.app.core.config import Settings, get_settings
from backend.app.db import session as db_session_module
from backend.app.db.models import AuditLog, ImportedFile, Run, ValidationResult, utc_now
from backend.app.imports.import_service import COMPANY_RESEARCH_RUN_TYPE, RunImportService

REPO_ROOT = Path(__file__).resolve().parents[3]
STATE_FILENAME = "company_research_state.json"
EVENTS_FILENAME = "company_research_events.jsonl"
MAX_LOG_EVENTS = 100
DEFAULT_TARGET_COMPANY_COUNT = 30
MAX_CONTINUATION_PROMPTS = 24
MIN_CONTINUATION_TIMEOUT_SECONDS = 15
MIN_PROMPT_TIMEOUT_SECONDS = 1

_RESEARCH_CLIENTS: dict[str, PiRpcClientProtocol] = {}
_RESEARCH_THREADS: dict[str, threading.Thread] = {}
_THREAD_LOCK = threading.Lock()


@dataclass(frozen=True)
class ResearchLaunchResult:
    run_id: str
    status: str
    command: list[str]
    workdir: Path


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _find_event_value(value: Any, keys: set[str]) -> Any:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in keys:
                return item
            nested = _find_event_value(item, keys)
            if nested is not None:
                return nested
    if isinstance(value, list):
        for item in value:
            nested = _find_event_value(item, keys)
            if nested is not None:
                return nested
    return None


def _latest_stop_reason(events: list[dict[str, Any]]) -> str | None:
    for event in reversed(events):
        reason = _find_event_value(event, {"stopReason", "stop_reason", "reason"})
        if reason:
            return str(reason)
    return None


def safe_research_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    allowed = {
        "APPDATA",
        "COMSPEC",
        "HOME",
        "LOCALAPPDATA",
        "PATH",
        "PATHEXT",
        "PI_CODING_AGENT_DIR",
        "PI_OFFLINE",
        "PI_SKIP_VERSION_CHECK",
        "PI_TELEMETRY",
        "PLAYWRIGHT_BROWSERS_PATH",
        "SYSTEMDRIVE",
        "SYSTEMROOT",
        "TEMP",
        "TMP",
        "USERPROFILE",
        "WINDIR",
    }
    env = {key: value for key, value in os.environ.items() if key.upper() in allowed}
    env["COMPANY_RESEARCH_REPO_ROOT"] = str(REPO_ROOT)
    env["COMPANY_RESEARCH_PYTHON"] = sys.executable
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(REPO_ROOT) if not existing_pythonpath else f"{REPO_ROOT}{os.pathsep}{existing_pythonpath}"
    if extra:
        env.update(extra)
    return env


def contain_path(root: Path, candidate: Path) -> Path:
    resolved_root = root.resolve()
    resolved_candidate = candidate.resolve()
    if resolved_candidate == resolved_root or not resolved_candidate.is_relative_to(resolved_root):
        raise ValueError("Path escapes company research workspace boundary")
    return resolved_candidate


class CompanyResearchRuntime:
    def __init__(
        self,
        *,
        settings: Settings | None = None,
        client_factory: ClientFactory | None = None,
        clients: dict[str, PiRpcClientProtocol] | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.client_factory = client_factory or self._default_client_factory
        self.clients = clients if clients is not None else _RESEARCH_CLIENTS

    def launch(self, run_id: str) -> ResearchLaunchResult:
        self._ensure_prepared_run(run_id)
        workspace = self._prepare_workspace(run_id)
        command = self._command(run_id)
        with _THREAD_LOCK:
            thread = _RESEARCH_THREADS.get(run_id)
            if thread is not None and thread.is_alive():
                return ResearchLaunchResult(run_id=run_id, status="running", command=command, workdir=workspace)
            self._write_state(run_id, "running", command=command, workdir=str(workspace), started_at=_utc_now())
            self._mark_run(run_id, "research_running", action="company_research_launch_started", result_status="started")
            thread = threading.Thread(target=self._run_agent, args=(run_id,), daemon=True)
            _RESEARCH_THREADS[run_id] = thread
            thread.start()
        return ResearchLaunchResult(run_id=run_id, status="running", command=command, workdir=workspace)

    def status(self, run_id: str) -> dict[str, Any]:
        state = self._read_state(run_id)
        run, validation_results, imported_files = self._read_import_state(run_id)
        status = self._display_status(state, run)
        return {
            "run_id": run_id,
            "runtime": "pi_rpc",
            "status": status,
            "state": state,
            "artifact_counts": self._artifact_counts(run_id),
            "validation": {
                "result_count": len(validation_results),
                "passed": sum(1 for item in validation_results if item.status == "schema_validation_passed"),
                "failed": sum(1 for item in validation_results if item.status != "schema_validation_passed"),
                "files": [
                    {
                        "filename": item.filename,
                        "status": item.status,
                        "schema_name": item.schema_name,
                        "error_count": item.error_count,
                        "reason_codes": json.loads(item.reason_codes_json),
                    }
                    for item in validation_results
                ],
            },
            "import_state": {
                "run_status": run.status if run is not None else None,
                "imported_file_count": len(imported_files),
                "output_path": run.output_path if run is not None else str(self._run_root(run_id) / "output"),
                "completed_at": run.completed_at.isoformat() if run is not None and run.completed_at else None,
            },
            "logs": self._tail_events(run_id),
        }

    def _display_status(self, state: dict[str, Any], run: Run | None) -> str:
        state_status = state.get("status")
        run_status = run.status if run is not None else None
        terminal_statuses = {"imported", "imported_with_errors", "import_failed", "research_failed", "failed"}
        if run_status in terminal_statuses:
            return run_status
        if run is not None and run.completed_at is not None and run_status:
            return run_status
        return state_status or run_status or "not_started"

    def _run_agent(self, run_id: str) -> None:
        try:
            prompt_timeout = self._prompt_timeout_seconds(run_id)
            target_company_count = self._target_company_count(run_id)
            started_monotonic = time.monotonic()
            continuation_count = 0
            final_reply = ""
            initial_counts = self._artifact_counts(run_id)
            self._write_state(
                run_id,
                "running",
                prompt_timeout_seconds=prompt_timeout,
                target_company_count=target_company_count,
                continuation_count=continuation_count,
                last_company_count=initial_counts["companies"],
                artifact_counts=initial_counts,
                elapsed_seconds=0,
            )
            if self._should_continue_research(
                counts=initial_counts,
                target_company_count=target_company_count,
                elapsed_seconds=0,
                prompt_timeout_seconds=prompt_timeout,
                continuation_count=continuation_count,
            ):
                if initial_counts["companies"] > 0:
                    self._import_research_artifacts(
                        run_id,
                        state_status="running",
                        counts=initial_counts,
                        target_company_count=target_company_count,
                        elapsed_seconds=0,
                        continuation_count=continuation_count,
                    )
                    self._mark_run(
                        run_id,
                        "research_running",
                        action="company_research_partial_import_completed",
                        result_status="completed",
                    )
                client = self._client(run_id)
                prompt = self._prompt(run_id)
                while True:
                    remaining_timeout = self._remaining_prompt_timeout(
                        started_monotonic,
                        prompt_timeout,
                    )
                    result = client.prompt(prompt, timeout_seconds=remaining_timeout)
                    final_reply = result.text
                    for event in result.events:
                        self._append_event(run_id, event)
                    counts = self._artifact_counts(run_id)
                    elapsed_seconds = round(time.monotonic() - started_monotonic, 3)
                    stop_reason = _latest_stop_reason(result.events)
                    self._write_state(
                        run_id,
                        "running",
                        last_reply=final_reply,
                        last_stop_reason=stop_reason,
                        last_company_count=counts["companies"],
                        artifact_counts=counts,
                        elapsed_seconds=elapsed_seconds,
                        continuation_count=continuation_count,
                    )
                    should_continue = self._should_continue_research(
                        counts=counts,
                        target_company_count=target_company_count,
                        elapsed_seconds=elapsed_seconds,
                        prompt_timeout_seconds=prompt_timeout,
                        continuation_count=continuation_count,
                    )
                    if not should_continue:
                        break
                    if counts["companies"] > 0:
                        self._import_research_artifacts(
                            run_id,
                            state_status="running",
                            counts=counts,
                            target_company_count=target_company_count,
                            elapsed_seconds=elapsed_seconds,
                            continuation_count=continuation_count,
                        )
                        self._mark_run(
                            run_id,
                            "research_running",
                            action="company_research_partial_import_completed",
                            result_status="completed",
                        )
                    continuation_count += 1
                    prompt = self._continuation_prompt(
                        run_id,
                        counts=counts,
                        target_company_count=target_company_count,
                        elapsed_seconds=elapsed_seconds,
                        remaining_seconds=max(prompt_timeout - elapsed_seconds, 0),
                        last_reply=final_reply,
                    )
                    self._append_event(
                        run_id,
                        {
                            "type": "company_research_continuation_requested",
                            "company_count": counts["companies"],
                            "target_company_count": target_company_count,
                            "continuation_count": continuation_count,
                            "elapsed_seconds": elapsed_seconds,
                        },
                    )
                    self._write_state(
                        run_id,
                        "continuing",
                        continuation_count=continuation_count,
                        last_company_count=counts["companies"],
                        elapsed_seconds=elapsed_seconds,
                    )
            else:
                final_reply = (
                    f"Skipped company research prompt because {initial_counts['companies']} existing company "
                    f"artifacts already meet target {target_company_count}."
                )
                self._append_event(
                    run_id,
                    {
                        "type": "company_research_target_already_met",
                        "company_count": initial_counts["companies"],
                        "target_company_count": target_company_count,
                        "elapsed_seconds": 0,
                    },
                )
            final_counts = self._artifact_counts(run_id)
            elapsed_seconds = round(time.monotonic() - started_monotonic, 3)
            self._write_state(run_id, "importing", last_reply=final_reply, importing_at=_utc_now())
            self._mark_run(run_id, "research_importing", action="company_research_agent_completed", result_status="completed")
            self._import_research_artifacts(
                run_id,
                state_status=None,
                counts=final_counts,
                target_company_count=target_company_count,
                elapsed_seconds=elapsed_seconds,
                continuation_count=continuation_count,
            )
        except Exception as exc:
            self._write_state(run_id, "failed", last_error=str(exc), failed_at=_utc_now(), error_type=type(exc).__name__)
            self._append_event(run_id, {"type": "company_research_failed", "error": str(exc), "error_type": type(exc).__name__})
            self._mark_run(run_id, "research_failed", action="company_research_failed", result_status="failed", reason_codes=["runtime_error"])
        finally:
            client = self.clients.pop(run_id, None)
            if client is not None:
                client.close()

    def _import_research_artifacts(
        self,
        run_id: str,
        *,
        state_status: str | None,
        counts: dict[str, int],
        target_company_count: int,
        elapsed_seconds: float,
        continuation_count: int,
    ) -> None:
        with Session(db_session_module.engine) as session:
            import_result = RunImportService(session=session, settings=self.settings).import_run(
                run_id,
                run_type=COMPANY_RESEARCH_RUN_TYPE,
            )
            self._write_state(
                run_id,
                state_status or import_result.run.status,
                imported_at=_utc_now(),
                import_status=import_result.run.status,
                validation_results=len(import_result.validation_results),
                artifact_counts=counts,
                last_company_count=counts["companies"],
                target_company_count=target_company_count,
                elapsed_seconds=elapsed_seconds,
                continuation_count=continuation_count,
            )

    def _ensure_prepared_run(self, run_id: str) -> None:
        with Session(db_session_module.engine) as session:
            run = session.exec(select(Run).where(Run.run_id == run_id)).first()
            if run is None:
                raise ValueError(f"Company research run is not prepared: {run_id}")
            if run.agent_type != "company_research":
                raise ValueError(f"Run is not a company research run: {run_id}")

    def _prepare_workspace(self, run_id: str) -> Path:
        run_root = self._run_root(run_id)
        workspace = run_root / "workspace"
        for dirname in ("input", "output", "logs", "workspace"):
            (run_root / dirname).mkdir(parents=True, exist_ok=True)
        (run_root / "output" / "companies").mkdir(parents=True, exist_ok=True)
        (run_root / "output" / "contacts").mkdir(parents=True, exist_ok=True)
        (run_root / "output" / "fit_evaluations").mkdir(parents=True, exist_ok=True)
        (workspace / "AGENTS.md").write_text(COMPANY_RESEARCH_INSTRUCTIONS, encoding="utf-8")
        (workspace / "README.md").write_text(
            (
                f"# Company Research Workspace\n\n"
                f"This folder is the dedicated Pi RPC workspace for research run `{run_id}`.\n"
                "Use the company_research_* tools, public web research, and the scoped shell. "
                "Read approved context from ../input and write JSON artifacts only under ../output/companies, "
                "../output/contacts, and ../output/fit_evaluations.\n"
            ),
            encoding="utf-8",
        )
        return workspace

    def _client(self, run_id: str) -> PiRpcClientProtocol:
        client = self.clients.get(run_id)
        if client is not None:
            return client
        workspace = self._workspace(run_id)
        client = self.client_factory(self._command(run_id), workspace, safe_research_env())
        self.clients[run_id] = client
        self._append_event(run_id, {"type": "pi_rpc_started", "command": self._logged_command(run_id)})
        return client

    def _default_client_factory(self, command: list[str], cwd: Path, env: dict[str, str]) -> PiRpcClientProtocol:
        return PiRpcClient.start(command, cwd, env)

    def _prompt(self, run_id: str) -> str:
        run_root = self._run_root(run_id)
        task = (run_root / "task.md").read_text(encoding="utf-8")
        instructions = (run_root / "instructions.md").read_text(encoding="utf-8")
        return (
            "Run the prepared company research task now.\n\n"
            "Instructions:\n"
            f"{instructions}\n\n"
            "Task:\n"
            f"{task}\n\n"
            "Use `company_research_list_inputs`, `company_research_read_input`, `company_research_shell`, "
            "`company_research_write_company`, `company_research_write_contact`, "
            "and `company_research_write_fit_evaluation` as needed. "
            "Stop after writing JSON artifacts. Do not create draft, send, Gmail, SMTP, or outreach files."
        )

    def _prompt_timeout_seconds(self, run_id: str) -> float:
        configured_timeout = self.settings.pi_rpc_research_timeout_seconds
        campaign = self._campaign(run_id)
        budget = campaign.get("time_budget_minutes") if isinstance(campaign, dict) else None
        if not isinstance(budget, int | float) or budget <= 0:
            return configured_timeout
        return min(configured_timeout, float(budget) * 60 + 60)

    def _campaign(self, run_id: str) -> dict[str, Any]:
        campaign_path = self._run_root(run_id) / "input" / "campaign.json"
        if not campaign_path.exists():
            return {}
        try:
            campaign = json.loads(campaign_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
        return campaign if isinstance(campaign, dict) else {}

    def _target_company_count(self, run_id: str) -> int:
        campaign = self._campaign(run_id)
        raw_target = campaign.get("max_companies")
        if isinstance(raw_target, int | float) and raw_target > 0:
            return min(int(raw_target), 100)
        return DEFAULT_TARGET_COMPANY_COUNT

    def _remaining_prompt_timeout(self, started_monotonic: float, prompt_timeout_seconds: float) -> float:
        elapsed = time.monotonic() - started_monotonic
        remaining = prompt_timeout_seconds - elapsed
        return max(remaining, MIN_PROMPT_TIMEOUT_SECONDS)

    def _should_continue_research(
        self,
        *,
        counts: dict[str, int],
        target_company_count: int,
        elapsed_seconds: float,
        prompt_timeout_seconds: float,
        continuation_count: int,
    ) -> bool:
        if counts["companies"] >= target_company_count:
            return False
        if elapsed_seconds >= prompt_timeout_seconds:
            return False
        if continuation_count >= MAX_CONTINUATION_PROMPTS:
            return False
        if prompt_timeout_seconds - elapsed_seconds < MIN_CONTINUATION_TIMEOUT_SECONDS:
            return False
        return True

    def _continuation_prompt(
        self,
        run_id: str,
        *,
        counts: dict[str, int],
        target_company_count: int,
        elapsed_seconds: float,
        remaining_seconds: float,
        last_reply: str,
    ) -> str:
        return (
            "Continue the prepared company research task. The previous reply stopped before the backend target was met.\n\n"
            f"Run ID: {run_id}\n"
            f"Current artifacts: {counts['companies']} companies, {counts['contacts']} contacts, "
            f"{counts['fit_evaluations']} fit evaluations.\n"
            f"Target company count: {target_company_count}.\n"
            f"Elapsed seconds: {round(elapsed_seconds, 1)}. Approximate remaining seconds: {round(remaining_seconds, 1)}.\n\n"
            "Do not import or send anything. Keep writing only company, contact, and fit evaluation JSON artifacts under ../output.\n"
            "Treat companies already present in ../input/existing_companies.json and ../output/companies as duplicates to avoid.\n"
            "If a public professional contact email is not found quickly, still write the company and fit evaluation and omit the contact file.\n"
            "Broaden discovery sources before stopping: relevant company directories, local startup ecosystems, funding/news pages, "
            "product-category searches, careers pages, and employer lists. Continue until the target count is reached or time expires.\n\n"
            "Previous final reply, for context only:\n"
            f"{last_reply[-4000:]}"
        )

    def _command(self, run_id: str) -> list[str]:
        provider = self.settings.pi_rpc_research_provider or self.settings.pi_rpc_provider
        model = self.settings.pi_rpc_research_model or self.settings.pi_rpc_model
        thinking = self.settings.pi_rpc_research_thinking or self.settings.pi_rpc_thinking
        command = [
            self.settings.pi_rpc_binary,
            "--mode",
            "rpc",
            "--session-dir",
            str(self._session_dir(run_id)),
            "--extension",
            str(self.settings.pi_rpc_research_extension_path),
        ]
        if self.settings.pi_rpc_no_builtin_tools:
            command.append("--no-builtin-tools")
        if provider:
            command.extend(["--provider", provider])
        if model:
            command.extend(["--model", model])
        if thinking:
            command.extend(["--thinking", thinking])
        return command

    def _logged_command(self, run_id: str) -> list[str]:
        return list(self._command(run_id))

    def _mark_run(
        self,
        run_id: str,
        status: str,
        *,
        action: str,
        result_status: str,
        reason_codes: list[str] | None = None,
    ) -> None:
        with Session(db_session_module.engine) as session:
            run = session.exec(select(Run).where(Run.run_id == run_id)).first()
            if run is None:
                return
            run.status = status
            run.agent_type = "company_research"
            run.updated_at = utc_now()
            if status == "research_running":
                run.started_at = run.started_at or utc_now()
                run.completed_at = None
            if status in {"research_failed"}:
                run.completed_at = utc_now()
            session.add(run)
            session.add(
                AuditLog(
                    run_id=run_id,
                    actor_type="backend",
                    action=action,
                    entity_type="run",
                    entity_id=run_id,
                    result_status=result_status,
                    reason_codes_json=_json_dumps(reason_codes or []),
                    metadata_json=_json_dumps({"runtime": "pi_rpc"}),
                )
            )
            session.commit()

    def _read_import_state(self, run_id: str) -> tuple[Run | None, list[ValidationResult], list[ImportedFile]]:
        with Session(db_session_module.engine) as session:
            run = session.exec(select(Run).where(Run.run_id == run_id)).first()
            validation_results = session.exec(
                select(ValidationResult).where(ValidationResult.run_id == run_id).order_by(ValidationResult.filename)
            ).all()
            imported_files = session.exec(select(ImportedFile).where(ImportedFile.run_id == run_id)).all()
            return run, list(validation_results), list(imported_files)

    def _artifact_counts(self, run_id: str) -> dict[str, int]:
        output = self._run_root(run_id) / "output"
        companies = output / "companies"
        contacts = output / "contacts"
        fits = output / "fit_evaluations"
        return {
            "companies": len([path for path in companies.glob("*.json") if path.is_file()]) if companies.exists() else 0,
            "contacts": len([path for path in contacts.glob("*.json") if path.is_file()]) if contacts.exists() else 0,
            "fit_evaluations": len([path for path in fits.glob("*.json") if path.is_file()]) if fits.exists() else 0,
            "unsupported_json": len(
                [
                    path
                    for path in output.rglob("*.json")
                    if path.is_file() and path.parent.name not in {"companies", "contacts", "fit_evaluations"}
                ]
            )
            if output.exists()
            else 0,
        }

    def _write_state(self, run_id: str, status: str, **extra: Any) -> None:
        current = self._read_state(run_id)
        current.update(extra)
        current["run_id"] = run_id
        current["runtime"] = "pi_rpc"
        current["status"] = status
        current["updated_at"] = _utc_now()
        path = self._state_path(run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def _read_state(self, run_id: str) -> dict[str, Any]:
        path = self._state_path(run_id)
        if not path.exists():
            return {"run_id": run_id, "runtime": "pi_rpc", "status": "not_started"}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"run_id": run_id, "runtime": "pi_rpc", "status": "unknown"}
        return data if isinstance(data, dict) else {"run_id": run_id, "runtime": "pi_rpc", "status": "unknown"}

    def _append_event(self, run_id: str, event: dict[str, Any]) -> None:
        path = self._events_path(run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as file:
            file.write(_json_dumps({"at": _utc_now(), **event}) + "\n")

    def _tail_events(self, run_id: str) -> list[dict[str, Any]]:
        path = self._events_path(run_id)
        if not path.exists():
            return []
        lines = path.read_text(encoding="utf-8").splitlines()[-MAX_LOG_EVENTS:]
        events: list[dict[str, Any]] = []
        for line in lines:
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                value = {"type": "parse_error", "raw": line}
            if isinstance(value, dict):
                events.append(value)
        return events

    def _run_root(self, run_id: str) -> Path:
        return self.settings.runs_root / run_id

    def _workspace(self, run_id: str) -> Path:
        return self._run_root(run_id) / "workspace"

    def _session_dir(self, run_id: str) -> Path:
        return self._run_root(run_id) / "logs" / "company-research-pi-session"

    def _state_path(self, run_id: str) -> Path:
        return self._run_root(run_id) / "logs" / STATE_FILENAME

    def _events_path(self, run_id: str) -> Path:
        return self._run_root(run_id) / "logs" / EVENTS_FILENAME
