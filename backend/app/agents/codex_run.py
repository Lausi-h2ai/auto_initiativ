from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlmodel import Session

from backend.app.agents.codex_exec import CodexExecAdapter, CodexExecResult, Runner
from backend.app.agents.run_folder import RunFolder, RunFolderGenerator, RunFolderSpec
from backend.app.core.config import Settings, get_settings
from backend.app.db.models import AuditLog
from backend.app.imports.import_service import ImportResult, RunImportService


@dataclass(frozen=True)
class CodexRunResult:
    folder: RunFolder
    execution: CodexExecResult
    import_result: ImportResult | None


class CodexRunService:
    def __init__(
        self,
        *,
        session: Session,
        settings: Settings | None = None,
        runner: Runner | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.runner = runner

    def prepare_execute_import(
        self,
        spec: RunFolderSpec,
        *,
        run_type: str | None = None,
        timeout_seconds: float | None = None,
    ) -> CodexRunResult:
        folder = RunFolderGenerator(settings=self.settings, session=self.session).prepare(spec)
        adapter_kwargs: dict[str, Any] = {"settings": self.settings, "session": self.session}
        if self.runner is not None:
            adapter_kwargs["runner"] = self.runner
        execution = CodexExecAdapter(**adapter_kwargs).run(folder.to_codex_exec_request(timeout_seconds=timeout_seconds))

        import_result = None
        if execution.status == "succeeded":
            import_result = RunImportService(session=self.session, settings=self.settings).import_run(spec.run_id, run_type=run_type)
        else:
            self._audit_import_skipped(spec.run_id, execution)
            self.session.commit()

        return CodexRunResult(folder=folder, execution=execution, import_result=import_result)

    def _audit_import_skipped(self, run_id: str, execution: CodexExecResult) -> None:
        self.session.add(
            AuditLog(
                run_id=run_id,
                actor_type="backend",
                action="codex_run_import_skipped",
                entity_type="run",
                entity_id=run_id,
                result_status="skipped",
                reason_codes_json=json.dumps([execution.failure_reason or execution.status], sort_keys=True),
                metadata_json=json.dumps(
                    {
                        "execution_status": execution.status,
                        "failure_reason": execution.failure_reason,
                        "log_path": str(execution.log_path),
                    },
                    sort_keys=True,
                ),
            )
        )
