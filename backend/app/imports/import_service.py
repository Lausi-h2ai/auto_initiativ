from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlmodel import Session, select

from backend.app.core.config import Settings, get_settings
from backend.app.db.models import AuditLog, ImportedFile, Run, ValidationResult, utc_now
from backend.app.imports.file_classifier import EXPECTED_FILENAMES, classify_filename
from backend.app.imports.validation import JsonValidationService, ValidationOutcome


DEFAULT_RUN_TYPE = "phase_1_full"
SUPPORTED_RUN_TYPES = {DEFAULT_RUN_TYPE: EXPECTED_FILENAMES}


@dataclass(frozen=True)
class ImportResult:
    run: Run
    validation_results: list[ValidationResult]


def _json_dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class RunImportService:
    def __init__(
        self,
        session: Session,
        settings: Settings | None = None,
        validator: JsonValidationService | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.validator = validator or JsonValidationService()

    def import_run(
        self,
        run_id: str,
        output_path: Path | None = None,
        run_type: str | None = None,
        expected_filenames: tuple[str, ...] = EXPECTED_FILENAMES,
    ) -> ImportResult:
        resolved_output_path = output_path or self.settings.runs_root / run_id / "output"
        run = self._get_or_create_run(run_id, resolved_output_path)
        if run_type is not None:
            run.agent_type = run_type
            if run_type not in SUPPORTED_RUN_TYPES:
                run.status = "import_failed"
                run.started_at = utc_now()
                run.completed_at = utc_now()
                run.updated_at = utc_now()
                self._audit(
                    run_id=run_id,
                    action="import_failed",
                    entity_type="run",
                    entity_id=run_id,
                    result_status="failed",
                    reason_codes=["unsupported_run_type"],
                    metadata={"run_type": run_type, "supported_run_types": sorted(SUPPORTED_RUN_TYPES)},
                )
                self.session.add(run)
                self.session.commit()
                self.session.refresh(run)
                return ImportResult(run=run, validation_results=[])

            expected_filenames = SUPPORTED_RUN_TYPES[run_type]

        run.status = "importing"
        run.started_at = utc_now()
        run.completed_at = None
        run.updated_at = utc_now()
        self._audit(
            run_id=run_id,
            action="import_started",
            entity_type="run",
            entity_id=run_id,
            result_status="started",
            metadata={"output_path": str(resolved_output_path)},
        )

        if not resolved_output_path.is_dir():
            run.status = "import_failed"
            run.completed_at = utc_now()
            run.updated_at = utc_now()
            self._audit(
                run_id=run_id,
                action="import_failed",
                entity_type="run",
                entity_id=run_id,
                result_status="failed",
                reason_codes=["missing_output_directory"],
                metadata={"output_path": str(resolved_output_path)},
            )
            self.session.add(run)
            self.session.commit()
            self.session.refresh(run)
            return ImportResult(run=run, validation_results=[])

        try:
            self._clear_previous_import_rows(run_id)

            results: list[ValidationResult] = []
            discovered_json_files = sorted(path for path in resolved_output_path.iterdir() if path.is_file() and path.suffix == ".json")

            for filename in expected_filenames:
                expected_path = resolved_output_path / filename
                if not expected_path.exists():
                    results.append(self._record_missing_expected_file(run_id, expected_path))

            for path in discovered_json_files:
                outcome = self.validator.validate_file(path)
                results.append(self._record_file_result(run_id, path, outcome))

            run.status = "imported" if all(result.status == "schema_validation_passed" for result in results) else "imported_with_errors"
            run.completed_at = utc_now()
            run.updated_at = utc_now()
            self.session.add(run)
            self._audit(
                run_id=run_id,
                action="import_completed",
                entity_type="run",
                entity_id=run_id,
                result_status=run.status,
                reason_codes=[] if run.status == "imported" else ["validation_errors_present"],
                metadata={"file_count": len(results)},
            )
            self.session.commit()
            self.session.refresh(run)
            for result in results:
                self.session.refresh(result)
            return ImportResult(run=run, validation_results=results)
        except Exception as exc:
            self.session.rollback()
            failed_run = self._get_or_create_run(run_id, resolved_output_path)
            failed_run.status = "import_failed"
            failed_run.completed_at = utc_now()
            failed_run.updated_at = utc_now()
            self.session.add(failed_run)
            self._audit(
                run_id=run_id,
                action="import_failed",
                entity_type="run",
                entity_id=run_id,
                result_status="failed",
                reason_codes=["import_exception"],
                metadata={"output_path": str(resolved_output_path), "error": str(exc), "error_type": type(exc).__name__},
            )
            self.session.commit()
            self.session.refresh(failed_run)
            return ImportResult(run=failed_run, validation_results=[])

    def _get_or_create_run(self, run_id: str, output_path: Path) -> Run:
        run = self.session.exec(select(Run).where(Run.run_id == run_id)).first()
        if run is None:
            run = Run(run_id=run_id, output_path=str(output_path), status="created")
        else:
            run.output_path = str(output_path)
        self.session.add(run)
        self.session.flush()
        return run

    def _clear_previous_import_rows(self, run_id: str) -> None:
        for validation_result in self.session.exec(select(ValidationResult).where(ValidationResult.run_id == run_id)).all():
            self.session.delete(validation_result)
        for imported_file in self.session.exec(select(ImportedFile).where(ImportedFile.run_id == run_id)).all():
            self.session.delete(imported_file)
        self.session.flush()

    def _record_missing_expected_file(self, run_id: str, path: Path) -> ValidationResult:
        schema_name = classify_filename(path.name)
        imported_file = ImportedFile(
            run_id=run_id,
            path=str(path),
            filename=path.name,
            schema_name=schema_name,
            sha256=None,
            size_bytes=0,
            status="missing_expected_file",
            raw_json=None,
        )
        self.session.add(imported_file)
        self.session.flush()
        result = ValidationResult(
            run_id=run_id,
            imported_file_id=imported_file.id,
            filename=path.name,
            status="missing_expected_file",
            schema_name=schema_name,
            error_count=1,
            errors_json=_json_dumps(
                [
                    {
                        "path": "$",
                        "message": f"Expected output file '{path.name}' is missing.",
                        "reason_code": "missing_expected_file",
                    }
                ]
            ),
            reason_codes_json=_json_dumps(["missing_expected_file"]),
        )
        self.session.add(result)
        self._audit(
            run_id=run_id,
            action="file_validation_failed",
            entity_type="imported_file",
            entity_id=path.name,
            result_status="missing_expected_file",
            reason_codes=["missing_expected_file"],
            metadata={"path": str(path), "schema_name": schema_name},
        )
        self.session.flush()
        return result

    def _record_file_result(self, run_id: str, path: Path, outcome: ValidationOutcome) -> ValidationResult:
        raw_json = _json_dumps(outcome.data) if isinstance(outcome.data, (dict, list)) else None
        imported_file = ImportedFile(
            run_id=run_id,
            path=str(path),
            filename=path.name,
            schema_name=outcome.schema_name,
            sha256=_sha256(path),
            size_bytes=path.stat().st_size,
            status=outcome.status,
            raw_json=raw_json,
        )
        self.session.add(imported_file)
        self.session.flush()
        result = ValidationResult(
            run_id=run_id,
            imported_file_id=imported_file.id,
            filename=path.name,
            status=outcome.status,
            schema_name=outcome.schema_name,
            error_count=outcome.error_count,
            errors_json=_json_dumps(outcome.errors),
            reason_codes_json=_json_dumps(outcome.reason_codes),
        )
        self.session.add(result)
        self._audit(
            run_id=run_id,
            action="file_validation_succeeded" if outcome.passed else "file_validation_failed",
            entity_type="imported_file",
            entity_id=path.name,
            result_status=outcome.status,
            reason_codes=outcome.reason_codes,
            metadata={"path": str(path), "schema_name": outcome.schema_name, "error_count": outcome.error_count},
        )
        self.session.flush()
        return result

    def _audit(
        self,
        run_id: str | None,
        action: str,
        entity_type: str,
        entity_id: str | None,
        result_status: str,
        reason_codes: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.session.add(
            AuditLog(
                run_id=run_id,
                actor_type="backend",
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                result_status=result_status,
                reason_codes_json=_json_dumps(reason_codes or []),
                metadata_json=_json_dumps(metadata or {}),
            )
        )
