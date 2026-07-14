from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlmodel import Session, select

from backend.app.auth.context import scoped_runs_root
from backend.app.core.config import Settings, get_settings
from backend.app.db.models import AuditLog, ImportedFile, Run, ValidationResult, utc_now
from backend.app.imports.domain_normalizer import DomainNormalizationService
from backend.app.imports.file_classifier import EXPECTED_FILENAMES, classify_output_path
from backend.app.imports.validation import JsonValidationService, ValidationOutcome


DEFAULT_RUN_TYPE = "phase_1_full"
ONBOARDING_CHAT_RUN_TYPE = "onboarding_chat"
COMPANY_RESEARCH_RUN_TYPE = "company_research"
APPLICATION_DRAFT_RUN_TYPE = "application_draft"
JOB_RESEARCH_RUN_TYPE = "job_research"
ONBOARDING_CHAT_FILENAMES = (
    "user_profile.json",
    "master_cv_profile.json",
    "policy.json",
    "onboarding_review.json",
)
COMPANY_RESEARCH_FILENAMES = (
    "companies/*.json",
    "contacts/*.json",
    "fit_evaluations/*.json",
)
APPLICATION_DRAFT_FILENAMES = ("email_draft.json",)
JOB_RESEARCH_FILENAMES = ("companies/*.json", "jobs/*.json", "job_fit_evaluations/*.json")
PASSING_VALIDATION_STATUSES = {"schema_validation_passed", "artifact_validation_passed"}
LEGACY_COMPANY_RESEARCH_FILENAMES = (
    "company_candidate.json",
    "contact_candidate.json",
    "fit_evaluation.json",
)
SUPPORTED_RUN_TYPES = {
    DEFAULT_RUN_TYPE: EXPECTED_FILENAMES,
    ONBOARDING_CHAT_RUN_TYPE: ONBOARDING_CHAT_FILENAMES,
    COMPANY_RESEARCH_RUN_TYPE: COMPANY_RESEARCH_FILENAMES,
    APPLICATION_DRAFT_RUN_TYPE: APPLICATION_DRAFT_FILENAMES,
    JOB_RESEARCH_RUN_TYPE: JOB_RESEARCH_FILENAMES,
}


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
        resolved_output_path = output_path or scoped_runs_root(self.settings.runs_root) / run_id / "output"
        run = self._get_or_create_run(run_id, resolved_output_path)
        if run_type is not None:
            run.agent_type = run_type
            expected_artifact_filenames: tuple[str, ...] = ()
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
            if run_type in {COMPANY_RESEARCH_RUN_TYPE, JOB_RESEARCH_RUN_TYPE}:
                expected_filenames = ()
            elif run_type == APPLICATION_DRAFT_RUN_TYPE:
                expected_filenames = self._application_draft_expected_json_files(run_id) or expected_filenames
                expected_artifact_filenames = self._application_draft_expected_artifact_files(run_id)
        else:
            expected_artifact_filenames = ()

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
            discovered_json_files = self._discover_json_files(resolved_output_path, run_type=run_type)
            if run_type in {COMPANY_RESEARCH_RUN_TYPE, JOB_RESEARCH_RUN_TYPE} and not discovered_json_files:
                for filename in SUPPORTED_RUN_TYPES[run_type]:
                    results.append(self._record_missing_expected_file(run_id, resolved_output_path / filename, filename=filename))

            for filename in expected_filenames:
                expected_path = resolved_output_path / filename
                if not expected_path.exists():
                    results.append(self._record_missing_expected_file(run_id, expected_path))

            for filename in expected_artifact_filenames:
                expected_path = resolved_output_path / filename
                if not expected_path.exists():
                    results.append(self._record_missing_expected_file(run_id, expected_path, filename=filename))
                else:
                    results.append(self._record_artifact_result(run_id, expected_path, filename=filename))

            for path, relative_path in discovered_json_files:
                outcome = self.validator.validate_file(path, relative_path=relative_path)
                results.append(self._record_file_result(run_id, path, outcome, filename=relative_path))

            run.status = "imported" if all(result.status in PASSING_VALIDATION_STATUSES for result in results) else "imported_with_errors"
            normalization_result = None
            normalization_metadata: dict[str, Any] | None = None
            should_normalize = run.status == "imported" or (
                run_type in {COMPANY_RESEARCH_RUN_TYPE, JOB_RESEARCH_RUN_TYPE}
                and any(result.status == "schema_validation_passed" for result in results)
            )
            if should_normalize:
                normalization_result = DomainNormalizationService(self.session).normalize_run(run_id)
                normalization_metadata = {
                    "status": normalization_result.status,
                    "counts": normalization_result.counts,
                    "unresolved_references": normalization_result.unresolved_references,
                }
                if normalization_result.reason_codes:
                    run.status = "imported_with_errors"
                if run_type == JOB_RESEARCH_RUN_TYPE:
                    from backend.app.imports.job_normalizer import JobNormalizationService
                    job_result = JobNormalizationService(self.session).normalize_run(run_id)
                    normalization_metadata["job_counts"] = job_result.counts
                    normalization_metadata["job_reason_codes"] = job_result.reason_codes
                    if job_result.reason_codes:
                        run.status = "imported_with_errors"
            run.completed_at = utc_now()
            run.updated_at = utc_now()
            self.session.add(run)
            self._audit(
                run_id=run_id,
                action="import_completed",
                entity_type="run",
                entity_id=run_id,
                result_status=run.status,
                reason_codes=(
                    []
                    if run.status == "imported"
                    else normalization_result.reason_codes
                    if normalization_metadata is not None
                    else ["validation_errors_present"]
                ),
                metadata={"file_count": len(results), "domain_normalization": normalization_metadata},
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
        DomainNormalizationService(self.session).clear_run_domain_rows(run_id)
        for validation_result in self.session.exec(select(ValidationResult).where(ValidationResult.run_id == run_id)).all():
            self.session.delete(validation_result)
        for imported_file in self.session.exec(select(ImportedFile).where(ImportedFile.run_id == run_id)).all():
            self.session.delete(imported_file)
        self.session.flush()

    def _discover_json_files(self, output_path: Path, *, run_type: str | None) -> list[tuple[Path, str]]:
        if run_type in {COMPANY_RESEARCH_RUN_TYPE, JOB_RESEARCH_RUN_TYPE}:
            files = [
                path
                for path in output_path.rglob("*.json")
                if path.is_file()
                and (
                    path.relative_to(output_path).as_posix() in LEGACY_COMPANY_RESEARCH_FILENAMES
                    or path.parent.name in {"companies", "contacts", "fit_evaluations", "jobs", "job_fit_evaluations"}
                )
            ]
        else:
            files = [path for path in output_path.iterdir() if path.is_file() and path.suffix == ".json"]
        return [
            (path, path.relative_to(output_path).as_posix())
            for path in sorted(files, key=lambda item: item.relative_to(output_path).as_posix())
        ]

    def _application_draft_expected_json_files(self, run_id: str) -> tuple[str, ...] | None:
        expected = self._application_draft_manifest_expected_files(run_id)
        if expected is None:
            return None
        filenames = [
            item
            for item in expected
            if "/" not in item.replace("\\", "/")
            and item.endswith(".json")
            and classify_output_path(item) is not None
        ]
        return tuple(dict.fromkeys(filenames)) or None

    def _application_draft_expected_artifact_files(self, run_id: str) -> tuple[str, ...]:
        expected = self._application_draft_manifest_expected_files(run_id)
        if expected is None:
            return ()
        filenames = [
            normalized
            for item in expected
            if isinstance(item, str)
            for normalized in (item.replace("\\", "/").strip("/"),)
            if normalized.startswith("attachments/")
            and normalized.count("/") == 1
            and normalized.lower().endswith((".html", ".pdf"))
        ]
        return tuple(dict.fromkeys(filenames))

    def _application_draft_manifest_expected_files(self, run_id: str) -> list[str] | None:
        manifest_path = scoped_runs_root(self.settings.runs_root) / run_id / "manifest.json"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        expected = manifest.get("expected_output_files")
        if not isinstance(expected, list):
            return None
        return [item for item in expected if isinstance(item, str)]

    def _record_artifact_result(self, run_id: str, path: Path, *, filename: str) -> ValidationResult:
        errors: list[dict[str, Any]] = []
        reason_codes: list[str] = []
        suffix = path.suffix.lower()
        size_bytes = path.stat().st_size
        if suffix == ".html":
            try:
                text = path.read_text(encoding="utf-8")
            except OSError as exc:
                text = ""
                errors.append({"path": "$", "message": str(exc), "reason_code": "file_read_failed"})
                reason_codes.append("file_read_failed")
            if text and ("<html" not in text.lower() or "@page" not in text.lower()):
                errors.append({"path": "$", "message": "Resume HTML must be a complete printable HTML document with @page CSS.", "reason_code": "invalid_resume_html"})
                reason_codes.append("invalid_resume_html")
            if text and any(pattern in text.lower() for pattern in ("transform:scale", "zoom:", "<canvas")):
                errors.append({"path": "$", "message": "Resume HTML uses disallowed global scaling or canvas rendering.", "reason_code": "invalid_resume_layout"})
                reason_codes.append("invalid_resume_layout")
        elif suffix == ".pdf":
            try:
                header = path.read_bytes()[:5]
            except OSError as exc:
                header = b""
                errors.append({"path": "$", "message": str(exc), "reason_code": "file_read_failed"})
                reason_codes.append("file_read_failed")
            if header != b"%PDF-":
                errors.append({"path": "$", "message": "Resume PDF must be a valid PDF file.", "reason_code": "invalid_pdf"})
                reason_codes.append("invalid_pdf")
            if size_bytes < 10_000:
                errors.append({"path": "$", "message": "Resume PDF is unexpectedly small.", "reason_code": "invalid_pdf"})
                reason_codes.append("invalid_pdf")
        status = "artifact_validation_failed" if errors else "artifact_validation_passed"
        reason_codes = sorted(set(reason_codes)) or ["artifact_validation_passed"]
        imported_file = ImportedFile(
            run_id=run_id,
            path=str(path),
            filename=filename,
            schema_name=None,
            sha256=_sha256(path),
            size_bytes=size_bytes,
            status=status,
            raw_json=None,
        )
        self.session.add(imported_file)
        self.session.flush()
        result = ValidationResult(
            run_id=run_id,
            imported_file_id=imported_file.id,
            filename=filename,
            status=status,
            schema_name=None,
            error_count=len(errors),
            errors_json=_json_dumps(errors),
            reason_codes_json=_json_dumps(reason_codes),
        )
        self.session.add(result)
        self._audit(
            run_id=run_id,
            action="file_validation_succeeded" if status == "artifact_validation_passed" else "file_validation_failed",
            entity_type="imported_file",
            entity_id=filename,
            result_status=status,
            reason_codes=reason_codes,
            metadata={"path": str(path), "schema_name": None, "error_count": len(errors)},
        )
        self.session.flush()
        return result

    def _record_missing_expected_file(self, run_id: str, path: Path, *, filename: str | None = None) -> ValidationResult:
        filename = filename or path.name
        schema_name = classify_output_path(filename)
        imported_file = ImportedFile(
            run_id=run_id,
            path=str(path),
            filename=filename,
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
            filename=filename,
            status="missing_expected_file",
            schema_name=schema_name,
            error_count=1,
            errors_json=_json_dumps(
                [
                    {
                        "path": "$",
                        "message": f"Expected output file '{filename}' is missing.",
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
            entity_id=filename,
            result_status="missing_expected_file",
            reason_codes=["missing_expected_file"],
            metadata={"path": str(path), "schema_name": schema_name},
        )
        self.session.flush()
        return result

    def _record_file_result(self, run_id: str, path: Path, outcome: ValidationOutcome, *, filename: str | None = None) -> ValidationResult:
        filename = filename or path.name
        raw_json = _json_dumps(outcome.data) if isinstance(outcome.data, (dict, list)) else None
        imported_file = ImportedFile(
            run_id=run_id,
            path=str(path),
            filename=filename,
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
            filename=filename,
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
            entity_id=filename,
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
