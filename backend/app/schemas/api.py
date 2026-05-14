from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class HealthResponse(BaseModel):
    status: str
    dry_run: bool


class ImportedFileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: str
    path: str
    filename: str
    schema_name: str | None
    sha256: str | None
    size_bytes: int
    status: str
    imported_at: datetime


class ValidationResultResponse(BaseModel):
    id: int
    run_id: str
    imported_file_id: int | None
    filename: str
    status: str
    schema_name: str | None
    error_count: int
    errors: list[dict[str, Any]]
    reason_codes: list[str]
    validated_at: datetime


class RunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: str
    agent_type: str | None
    output_path: str
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class RunDetailResponse(RunResponse):
    files: list[ImportedFileResponse]


class ImportSummaryItem(BaseModel):
    filename: str
    status: str
    schema_name: str | None
    error_count: int
    reason_codes: list[str]


class ImportResponse(BaseModel):
    run: RunResponse
    results: list[ImportSummaryItem]


class AuditLogResponse(BaseModel):
    id: int
    run_id: str | None
    actor_type: str
    action: str
    entity_type: str
    entity_id: str | None
    result_status: str
    reason_codes: list[str]
    metadata: dict[str, Any]
    created_at: datetime


class GateEvaluationResponse(BaseModel):
    gate_result_id: str
    intent_id: str
    status: str
    checks: list[dict[str, str]]
    reasons: list[dict[str, str]]
    evaluated_at: datetime
    policy_snapshot_id: str | None
