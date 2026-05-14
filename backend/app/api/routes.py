from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlmodel import Session, select

from backend.app.core.config import get_settings
from backend.app.db.models import (
    AuditLog,
    Company,
    Contact,
    EmailDraft,
    FitEvaluation,
    ImportedFile,
    ImportedGateResult,
    OutreachRecord,
    Run,
    SendIntent,
    ValidationResult,
)
from backend.app.db.session import get_session
from backend.app.gates.evaluate_only import EvaluateOnlyGateService
from backend.app.imports.import_service import RunImportService
from backend.app.schemas.api import (
    AuditLogResponse,
    CompanyResponse,
    ContactResponse,
    DashboardSummaryResponse,
    EmailDraftResponse,
    FitEvaluationResponse,
    GateEvaluationResponse,
    GateResultResponse,
    GateResultSummaryResponse,
    HealthResponse,
    ImportedFileResponse,
    ImportResponse,
    ImportSummaryItem,
    OutreachRecordResponse,
    RunDetailResponse,
    RunResponse,
    SendIntentResponse,
    ValidationResultResponse,
)

router = APIRouter()


def _json_loads(value: str, fallback: Any) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def _json_has_items(value: str) -> bool:
    decoded = _json_loads(value, [])
    return isinstance(decoded, list) and len(decoded) > 0


def _matches_json_flag(value: str, expected: bool | None) -> bool:
    if expected is None:
        return True
    return _json_has_items(value) == expected


def _matches_reason_code(checks_json: str, reasons_json: str, reason_code: str | None) -> bool:
    if reason_code is None:
        return True
    values = _json_loads(reasons_json, []) + _json_loads(checks_json, [])
    if not isinstance(values, list):
        return False
    for value in values:
        if isinstance(value, dict) and value.get("code") == reason_code:
            return True
        if value == reason_code:
            return True
    return False


def _imported_file_ids_for_run(session: Session, run_id: str) -> set[int]:
    files = session.exec(select(ImportedFile.id).where(ImportedFile.run_id == run_id)).all()
    return {file_id for file_id in files if file_id is not None}


def _matches_import_run(imported_file_id: int | None, imported_file_ids: set[int] | None) -> bool:
    if imported_file_ids is None:
        return True
    return imported_file_id in imported_file_ids


def _not_found(entity_name: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"{entity_name} not found")


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


def _company_response(company: Company) -> CompanyResponse:
    return CompanyResponse(
        id=company.id or 0,
        company_id=company.company_id,
        name=company.name,
        raw_domain=company.raw_domain,
        normalized_domain=company.normalized_domain,
        normalized_name=company.normalized_name,
        company_policy_key=company.company_policy_key,
        company_policy_key_kind=company.company_policy_key_kind,
        description=company.description,
        industry_tags=_json_loads(company.industry_tags_json, []),
        locations=_json_loads(company.locations_json, []),
        remote_policy=company.remote_policy,
        source_refs=_json_loads(company.source_refs_json, []),
        confidence=company.confidence,
        review_flags=_json_loads(company.review_flags_json, []),
        policy_conflicts=_json_loads(company.policy_conflicts_json, []),
        raw=_json_loads(company.raw_json, {}),
        imported_file_id=company.imported_file_id,
        created_at=company.created_at,
        updated_at=company.updated_at,
    )


def _contact_response(contact: Contact) -> ContactResponse:
    return ContactResponse(
        id=contact.id or 0,
        contact_id=contact.contact_id,
        company_id=contact.company_id,
        external_company_id=contact.external_company_id,
        name=contact.name,
        role_title=contact.role_title,
        raw_email=contact.raw_email,
        normalized_recipient_email=contact.normalized_recipient_email,
        email_source=contact.email_source,
        profile_url=contact.profile_url,
        source_refs=_json_loads(contact.source_refs_json, []),
        confidence=contact.confidence,
        review_flags=_json_loads(contact.review_flags_json, []),
        raw=_json_loads(contact.raw_json, {}),
        imported_file_id=contact.imported_file_id,
        created_at=contact.created_at,
        updated_at=contact.updated_at,
    )


def _fit_evaluation_response(evaluation: FitEvaluation) -> FitEvaluationResponse:
    return FitEvaluationResponse(
        id=evaluation.id or 0,
        evaluation_id=evaluation.evaluation_id,
        company_id=evaluation.company_id,
        external_company_id=evaluation.external_company_id,
        user_profile_snapshot_id=evaluation.user_profile_snapshot_id,
        policy_snapshot_id=evaluation.policy_snapshot_id,
        fit_score=evaluation.fit_score,
        decision=evaluation.decision,
        reasons=_json_loads(evaluation.reasons_json, []),
        risks=_json_loads(evaluation.risks_json, []),
        source_refs=_json_loads(evaluation.source_refs_json, []),
        confidence=evaluation.confidence,
        review_flags=_json_loads(evaluation.review_flags_json, []),
        raw=_json_loads(evaluation.raw_json, {}),
        imported_file_id=evaluation.imported_file_id,
        created_at=evaluation.created_at,
    )


def _email_draft_response(draft: EmailDraft) -> EmailDraftResponse:
    return EmailDraftResponse(
        id=draft.id or 0,
        draft_id=draft.draft_id,
        company_id=draft.company_id,
        external_company_id=draft.external_company_id,
        contact_id=draft.contact_id,
        external_contact_id=draft.external_contact_id,
        subject=draft.subject,
        body_text=draft.body_text,
        body_html=draft.body_html,
        tone=draft.tone,
        claim_refs=_json_loads(draft.claim_refs_json, []),
        source_refs=_json_loads(draft.source_refs_json, []),
        attachments=_json_loads(draft.attachments_json, []),
        confidence=draft.confidence,
        review_flags=_json_loads(draft.review_flags_json, []),
        raw=_json_loads(draft.raw_json, {}),
        imported_file_id=draft.imported_file_id,
        created_at=draft.created_at,
    )


def _latest_gate_result(session: Session, intent_id: str) -> ImportedGateResult | None:
    return session.exec(
        select(ImportedGateResult)
        .where(ImportedGateResult.external_intent_id == intent_id)
        .order_by(ImportedGateResult.evaluated_at.desc())
    ).first()


def _latest_gate_result_summary(session: Session, intent_id: str) -> GateResultSummaryResponse | None:
    gate_result = _latest_gate_result(session, intent_id)
    if gate_result is None:
        return None
    return GateResultSummaryResponse(
        gate_result_id=gate_result.gate_result_id,
        status=gate_result.status,
        evaluated_at=gate_result.evaluated_at,
        reasons=_json_loads(gate_result.reasons_json, []),
    )


def _send_intent_response(intent: SendIntent, session: Session) -> SendIntentResponse:
    return SendIntentResponse(
        id=intent.id or 0,
        intent_id=intent.intent_id,
        run_id=intent.run_id,
        company_id=intent.company_id,
        external_company_id=intent.external_company_id,
        contact_id=intent.contact_id,
        external_contact_id=intent.external_contact_id,
        email_draft_id=intent.email_draft_id,
        external_email_draft_id=intent.external_email_draft_id,
        raw_recipient_email=intent.raw_recipient_email,
        normalized_recipient_email=intent.normalized_recipient_email,
        recipient_name=intent.recipient_name,
        company_domain=intent.company_domain,
        subject=intent.subject,
        body_text=intent.body_text,
        body_html=intent.body_html,
        attachments=_json_loads(intent.attachments_json, []),
        source_refs=_json_loads(intent.source_refs_json, []),
        claim_refs=_json_loads(intent.claim_refs_json, []),
        policy_snapshot_id=intent.policy_snapshot_id,
        external_policy_id=intent.external_policy_id,
        user_profile_snapshot_id=intent.user_profile_snapshot_id,
        external_profile_id=intent.external_profile_id,
        master_cv_profile_snapshot_id=intent.master_cv_profile_snapshot_id,
        external_master_cv_profile_id=intent.external_master_cv_profile_id,
        confidence=intent.confidence,
        review_flags=_json_loads(intent.review_flags_json, []),
        created_by=intent.created_by,
        status=intent.status,
        raw=_json_loads(intent.raw_json, {}),
        imported_file_id=intent.imported_file_id,
        created_at=intent.created_at,
        updated_at=intent.updated_at,
        latest_gate_result=_latest_gate_result_summary(session, intent.intent_id),
    )


def _gate_result_response(gate_result: ImportedGateResult) -> GateResultResponse:
    return GateResultResponse(
        id=gate_result.id or 0,
        gate_result_id=gate_result.gate_result_id,
        send_intent_id=gate_result.send_intent_id,
        external_intent_id=gate_result.external_intent_id,
        status=gate_result.status,
        checks=_json_loads(gate_result.checks_json, []),
        reasons=_json_loads(gate_result.reasons_json, []),
        external_reservation_id=gate_result.external_reservation_id,
        evaluated_at=gate_result.evaluated_at,
        policy_snapshot_id=gate_result.policy_snapshot_id,
        external_policy_id=gate_result.external_policy_id,
        raw=_json_loads(gate_result.raw_json, {}),
        imported_file_id=gate_result.imported_file_id,
        imported_at=gate_result.imported_at,
    )


def _outreach_record_response(record: OutreachRecord) -> OutreachRecordResponse:
    return OutreachRecordResponse(
        id=record.id or 0,
        outreach_record_id=record.outreach_record_id,
        send_intent_id=record.send_intent_id,
        company_id=record.company_id,
        contact_id=record.contact_id,
        normalized_recipient_email=record.normalized_recipient_email,
        company_policy_key=record.company_policy_key,
        policy_snapshot_id=record.policy_snapshot_id,
        channel=record.channel,
        status=record.status,
        dedupe_recipient=record.dedupe_recipient,
        dedupe_company=record.dedupe_company,
        occurred_at=record.occurred_at,
        source=record.source,
        notes=_json_loads(record.notes_json, {}),
    )


def _count_by_status(session: Session, model: type[Any], status_column: Any) -> dict[str, int]:
    rows = session.exec(select(status_column, func.count(model.id)).group_by(status_column)).all()
    return {status: count for status, count in rows}


def _count(session: Session, model: type[Any]) -> int:
    return session.exec(select(func.count(model.id))).one()


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


@router.get("/dashboard/summary", response_model=DashboardSummaryResponse)
def dashboard_summary(session: Session = Depends(get_session)) -> DashboardSummaryResponse:
    return DashboardSummaryResponse(
        runs=_count(session, Run),
        companies=_count(session, Company),
        contacts=_count(session, Contact),
        fit_evaluations=_count(session, FitEvaluation),
        email_drafts=_count(session, EmailDraft),
        send_intents=_count(session, SendIntent),
        gate_results=_count(session, ImportedGateResult),
        outreach_records=_count(session, OutreachRecord),
        send_intents_by_status=_count_by_status(session, SendIntent, SendIntent.status),
        gate_results_by_status=_count_by_status(session, ImportedGateResult, ImportedGateResult.status),
        outreach_records_by_status=_count_by_status(session, OutreachRecord, OutreachRecord.status),
    )


@router.get("/companies", response_model=list[CompanyResponse])
def list_companies(
    run_id: str | None = None,
    min_confidence: float | None = Query(default=None, ge=0, le=1),
    has_review_flags: bool | None = None,
    has_policy_conflicts: bool | None = None,
    session: Session = Depends(get_session),
) -> list[CompanyResponse]:
    imported_file_ids = _imported_file_ids_for_run(session, run_id) if run_id is not None else None
    companies = session.exec(select(Company).order_by(Company.created_at.desc(), Company.name)).all()
    return [
        _company_response(company)
        for company in companies
        if _matches_import_run(company.imported_file_id, imported_file_ids)
        and (min_confidence is None or company.confidence >= min_confidence)
        and _matches_json_flag(company.review_flags_json, has_review_flags)
        and _matches_json_flag(company.policy_conflicts_json, has_policy_conflicts)
    ]


@router.get("/companies/{company_id}", response_model=CompanyResponse)
def get_company(company_id: str, session: Session = Depends(get_session)) -> CompanyResponse:
    company = session.exec(select(Company).where(Company.company_id == company_id)).first()
    if company is None:
        raise _not_found("Company")
    return _company_response(company)


@router.get("/contacts", response_model=list[ContactResponse])
def list_contacts(
    run_id: str | None = None,
    company_id: str | None = None,
    email_source: str | None = None,
    min_confidence: float | None = Query(default=None, ge=0, le=1),
    has_review_flags: bool | None = None,
    session: Session = Depends(get_session),
) -> list[ContactResponse]:
    imported_file_ids = _imported_file_ids_for_run(session, run_id) if run_id is not None else None
    contacts = session.exec(select(Contact).order_by(Contact.created_at.desc(), Contact.contact_id)).all()
    return [
        _contact_response(contact)
        for contact in contacts
        if _matches_import_run(contact.imported_file_id, imported_file_ids)
        and (company_id is None or contact.external_company_id == company_id)
        and (email_source is None or contact.email_source == email_source)
        and (min_confidence is None or contact.confidence >= min_confidence)
        and _matches_json_flag(contact.review_flags_json, has_review_flags)
    ]


@router.get("/contacts/{contact_id}", response_model=ContactResponse)
def get_contact(contact_id: str, session: Session = Depends(get_session)) -> ContactResponse:
    contact = session.exec(select(Contact).where(Contact.contact_id == contact_id)).first()
    if contact is None:
        raise _not_found("Contact")
    return _contact_response(contact)


@router.get("/fit-evaluations", response_model=list[FitEvaluationResponse])
def list_fit_evaluations(
    run_id: str | None = None,
    company_id: str | None = None,
    decision: str | None = None,
    min_confidence: float | None = Query(default=None, ge=0, le=1),
    has_review_flags: bool | None = None,
    session: Session = Depends(get_session),
) -> list[FitEvaluationResponse]:
    imported_file_ids = _imported_file_ids_for_run(session, run_id) if run_id is not None else None
    evaluations = session.exec(select(FitEvaluation).order_by(FitEvaluation.created_at.desc())).all()
    return [
        _fit_evaluation_response(evaluation)
        for evaluation in evaluations
        if _matches_import_run(evaluation.imported_file_id, imported_file_ids)
        and (company_id is None or evaluation.external_company_id == company_id)
        and (decision is None or evaluation.decision == decision)
        and (min_confidence is None or evaluation.confidence >= min_confidence)
        and _matches_json_flag(evaluation.review_flags_json, has_review_flags)
    ]


@router.get("/fit-evaluations/{evaluation_id}", response_model=FitEvaluationResponse)
def get_fit_evaluation(evaluation_id: str, session: Session = Depends(get_session)) -> FitEvaluationResponse:
    evaluation = session.exec(select(FitEvaluation).where(FitEvaluation.evaluation_id == evaluation_id)).first()
    if evaluation is None:
        raise _not_found("Fit evaluation")
    return _fit_evaluation_response(evaluation)


@router.get("/email-drafts", response_model=list[EmailDraftResponse])
def list_email_drafts(
    run_id: str | None = None,
    company_id: str | None = None,
    contact_id: str | None = None,
    min_confidence: float | None = Query(default=None, ge=0, le=1),
    has_review_flags: bool | None = None,
    session: Session = Depends(get_session),
) -> list[EmailDraftResponse]:
    imported_file_ids = _imported_file_ids_for_run(session, run_id) if run_id is not None else None
    drafts = session.exec(select(EmailDraft).order_by(EmailDraft.created_at.desc(), EmailDraft.draft_id)).all()
    return [
        _email_draft_response(draft)
        for draft in drafts
        if _matches_import_run(draft.imported_file_id, imported_file_ids)
        and (company_id is None or draft.external_company_id == company_id)
        and (contact_id is None or draft.external_contact_id == contact_id)
        and (min_confidence is None or draft.confidence >= min_confidence)
        and _matches_json_flag(draft.review_flags_json, has_review_flags)
    ]


@router.get("/email-drafts/{draft_id}", response_model=EmailDraftResponse)
def get_email_draft(draft_id: str, session: Session = Depends(get_session)) -> EmailDraftResponse:
    draft = session.exec(select(EmailDraft).where(EmailDraft.draft_id == draft_id)).first()
    if draft is None:
        raise _not_found("Email draft")
    return _email_draft_response(draft)


@router.get("/send-intents", response_model=list[SendIntentResponse])
def list_send_intents(
    run_id: str | None = None,
    company_id: str | None = None,
    contact_id: str | None = None,
    status: str | None = None,
    gate_status: str | None = None,
    reason_code: str | None = None,
    min_confidence: float | None = Query(default=None, ge=0, le=1),
    has_review_flags: bool | None = None,
    session: Session = Depends(get_session),
) -> list[SendIntentResponse]:
    statement = select(SendIntent)
    if run_id is not None:
        statement = statement.where(SendIntent.run_id == run_id)
    if company_id is not None:
        statement = statement.where(SendIntent.external_company_id == company_id)
    if contact_id is not None:
        statement = statement.where(SendIntent.external_contact_id == contact_id)
    if status is not None:
        statement = statement.where(SendIntent.status == status)
    if min_confidence is not None:
        statement = statement.where(SendIntent.confidence >= min_confidence)
    intents = session.exec(statement.order_by(SendIntent.created_at.desc(), SendIntent.intent_id)).all()
    responses: list[SendIntentResponse] = []
    for intent in intents:
        latest_gate_result = _latest_gate_result(session, intent.intent_id)
        if not _matches_json_flag(intent.review_flags_json, has_review_flags):
            continue
        if gate_status is not None and (latest_gate_result is None or latest_gate_result.status != gate_status):
            continue
        if reason_code is not None and (
            latest_gate_result is None
            or not _matches_reason_code(latest_gate_result.checks_json, latest_gate_result.reasons_json, reason_code)
        ):
            continue
        responses.append(_send_intent_response(intent, session))
    return responses


@router.get("/send-intents/{intent_id}", response_model=SendIntentResponse)
def get_send_intent(intent_id: str, session: Session = Depends(get_session)) -> SendIntentResponse:
    intent = session.exec(select(SendIntent).where(SendIntent.intent_id == intent_id)).first()
    if intent is None:
        raise _not_found("Send intent")
    return _send_intent_response(intent, session)


@router.get("/gate-results", response_model=list[GateResultResponse])
def list_gate_results(
    run_id: str | None = None,
    company_id: str | None = None,
    contact_id: str | None = None,
    intent_id: str | None = None,
    status: str | None = None,
    gate_status: str | None = None,
    reason_code: str | None = None,
    session: Session = Depends(get_session),
) -> list[GateResultResponse]:
    results = session.exec(select(ImportedGateResult).order_by(ImportedGateResult.evaluated_at.desc())).all()
    responses: list[GateResultResponse] = []
    for result in results:
        intent = session.get(SendIntent, result.send_intent_id) if result.send_intent_id is not None else None
        if run_id is not None and (intent is None or intent.run_id != run_id):
            continue
        if company_id is not None and (intent is None or intent.external_company_id != company_id):
            continue
        if contact_id is not None and (intent is None or intent.external_contact_id != contact_id):
            continue
        expected_status = gate_status or status
        if expected_status is not None and result.status != expected_status:
            continue
        if intent_id is not None and result.external_intent_id != intent_id:
            continue
        if not _matches_reason_code(result.checks_json, result.reasons_json, reason_code):
            continue
        responses.append(_gate_result_response(result))
    return responses


@router.get("/gate-results/{gate_result_id}", response_model=GateResultResponse)
def get_gate_result(gate_result_id: str, session: Session = Depends(get_session)) -> GateResultResponse:
    result = session.exec(select(ImportedGateResult).where(ImportedGateResult.gate_result_id == gate_result_id)).first()
    if result is None:
        raise _not_found("Gate result")
    return _gate_result_response(result)


@router.get("/send-intents/{intent_id}/gate-results", response_model=list[GateResultResponse])
def list_send_intent_gate_results(intent_id: str, session: Session = Depends(get_session)) -> list[GateResultResponse]:
    intent = session.exec(select(SendIntent).where(SendIntent.intent_id == intent_id)).first()
    if intent is None:
        raise _not_found("Send intent")
    results = session.exec(
        select(ImportedGateResult)
        .where(ImportedGateResult.external_intent_id == intent_id)
        .order_by(ImportedGateResult.evaluated_at.desc())
    ).all()
    return [_gate_result_response(result) for result in results]


@router.get("/outreach-records", response_model=list[OutreachRecordResponse])
def list_outreach_records(
    run_id: str | None = None,
    company_id: str | None = None,
    contact_id: str | None = None,
    status: str | None = None,
    session: Session = Depends(get_session),
) -> list[OutreachRecordResponse]:
    records = session.exec(select(OutreachRecord).order_by(OutreachRecord.occurred_at.desc())).all()
    responses: list[OutreachRecordResponse] = []
    for record in records:
        intent = session.get(SendIntent, record.send_intent_id) if record.send_intent_id is not None else None
        company = session.get(Company, record.company_id) if record.company_id is not None else None
        contact = session.get(Contact, record.contact_id) if record.contact_id is not None else None
        if run_id is not None and (intent is None or intent.run_id != run_id):
            continue
        if company_id is not None and (company is None or company.company_id != company_id):
            continue
        if contact_id is not None and (contact is None or contact.contact_id != contact_id):
            continue
        if status is not None and record.status != status:
            continue
        responses.append(_outreach_record_response(record))
    return responses


@router.get("/outreach-records/{outreach_record_id}", response_model=OutreachRecordResponse)
def get_outreach_record(outreach_record_id: str, session: Session = Depends(get_session)) -> OutreachRecordResponse:
    record = session.exec(select(OutreachRecord).where(OutreachRecord.outreach_record_id == outreach_record_id)).first()
    if record is None:
        raise _not_found("Outreach record")
    return _outreach_record_response(record)


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
    entity_id: str | None = None,
    action: str | None = None,
    result_status: str | None = None,
    reason_code: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_session),
) -> list[AuditLogResponse]:
    statement = select(AuditLog)
    if run_id is not None:
        statement = statement.where(AuditLog.run_id == run_id)
    if entity_type is not None:
        statement = statement.where(AuditLog.entity_type == entity_type)
    if entity_id is not None:
        statement = statement.where(AuditLog.entity_id == entity_id)
    if action is not None:
        statement = statement.where(AuditLog.action == action)
    if result_status is not None:
        statement = statement.where(AuditLog.result_status == result_status)
    logs = session.exec(statement.order_by(AuditLog.created_at.desc()).limit(limit)).all()
    return [_audit_response(log) for log in logs if _matches_reason_code("[]", log.reason_codes_json, reason_code)]
