from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from backend.app.core.config import get_settings
from backend.app.db.models import AuditLog, ImportedFile, Run, ValidationResult
from backend.app.db.session import get_session
from backend.app.gates.evaluate_only import EvaluateOnlyGateService
from backend.app.imports.import_service import RunImportService
from backend.app.schemas.api import (
    AuditLogResponse,
    GateEvaluationResponse,
    HealthResponse,
    ImportedFileResponse,
    ImportResponse,
    ImportSummaryItem,
    RunDetailResponse,
    RunResponse,
    ValidationResultResponse,
)

router = APIRouter()


def _json_loads(value: str, fallback: Any) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def _validation_response(result: ValidationResult) -> ValidationResultResponse:
    return ValidationResultResponse(
        id=result.id or 0,
        run_id=result.run_id,
        imported_file_id=result.imported_file_id,
        filename=result.filename,
        status=result.status,
        schema_name=result.schema_name,
        error_count=result.error_count,
        errors=_json_loads(result.errors_json, []),
        reason_codes=_json_loads(result.reason_codes_json, []),
        validated_at=result.validated_at,
    )


def _audit_response(log: AuditLog) -> AuditLogResponse:
    return AuditLogResponse(
        id=log.id or 0,
        run_id=log.run_id,
        actor_type=log.actor_type,
        action=log.action,
        entity_type=log.entity_type,
        entity_id=log.entity_id,
        result_status=log.result_status,
        reason_codes=_json_loads(log.reason_codes_json, []),
        metadata=_json_loads(log.metadata_json, {}),
        created_at=log.created_at,
    )


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", dry_run=get_settings().dry_run)


@router.post("/runs/{run_id}/import", response_model=ImportResponse)
def import_run(run_id: str, run_type: str | None = None, session: Session = Depends(get_session)) -> ImportResponse:
    result = RunImportService(session=session).import_run(run_id, run_type=run_type)
    return ImportResponse(
        run=RunResponse.model_validate(result.run),
        results=[
            ImportSummaryItem(
                filename=validation_result.filename,
                status=validation_result.status,
                schema_name=validation_result.schema_name,
                error_count=validation_result.error_count,
                reason_codes=_json_loads(validation_result.reason_codes_json, []),
            )
            for validation_result in result.validation_results
        ],
    )


@router.get("/runs", response_model=list[RunResponse])
def list_runs(session: Session = Depends(get_session)) -> list[RunResponse]:
    runs = session.exec(select(Run).order_by(Run.created_at.desc())).all()
    return [RunResponse.model_validate(run) for run in runs]


@router.get("/runs/{run_id}", response_model=RunDetailResponse)
def get_run(run_id: str, session: Session = Depends(get_session)) -> RunDetailResponse:
    run = session.exec(select(Run).where(Run.run_id == run_id)).first()
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    files = session.exec(select(ImportedFile).where(ImportedFile.run_id == run_id).order_by(ImportedFile.filename)).all()
    return RunDetailResponse(**RunResponse.model_validate(run).model_dump(), files=[ImportedFileResponse.model_validate(file) for file in files])


@router.get("/runs/{run_id}/files", response_model=list[ImportedFileResponse])
def list_run_files(run_id: str, session: Session = Depends(get_session)) -> list[ImportedFileResponse]:
    files = session.exec(select(ImportedFile).where(ImportedFile.run_id == run_id).order_by(ImportedFile.filename)).all()
    return [ImportedFileResponse.model_validate(file) for file in files]


@router.get("/runs/{run_id}/validation-results", response_model=list[ValidationResultResponse])
def list_validation_results(run_id: str, session: Session = Depends(get_session)) -> list[ValidationResultResponse]:
    results = session.exec(select(ValidationResult).where(ValidationResult.run_id == run_id).order_by(ValidationResult.filename)).all()
    return [_validation_response(result) for result in results]


@router.post("/gate/evaluations/{intent_id}", response_model=GateEvaluationResponse)
def evaluate_gate(intent_id: str, session: Session = Depends(get_session)) -> GateEvaluationResponse:
    try:
        result = EvaluateOnlyGateService(session=session).evaluate(intent_id)
        session.commit()
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return GateEvaluationResponse(
        gate_result_id=result.gate_result.gate_result_id,
        intent_id=result.gate_result.external_intent_id,
        status=result.gate_result.status,
        checks=result.checks,
        reasons=result.reasons,
        evaluated_at=result.gate_result.evaluated_at,
        policy_snapshot_id=result.gate_result.external_policy_id,
    )


@router.get("/audit-logs", response_model=list[AuditLogResponse])
def list_audit_logs(
    run_id: str | None = None,
    entity_type: str | None = None,
    action: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_session),
) -> list[AuditLogResponse]:
    statement = select(AuditLog)
    if run_id is not None:
        statement = statement.where(AuditLog.run_id == run_id)
    if entity_type is not None:
        statement = statement.where(AuditLog.entity_type == entity_type)
    if action is not None:
        statement = statement.where(AuditLog.action == action)
    logs = session.exec(statement.order_by(AuditLog.created_at.desc()).limit(limit)).all()
    return [_audit_response(log) for log in logs]
