from __future__ import annotations

import json
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlmodel import Session, col, select

from backend.app.auth.context import current_identity, scoped_runs_root
from backend.app.agents.codex_tmux import TmuxCodexBridge, TmuxCodexError, TmuxTarget
from backend.app.agents.company_research import (
    COMPANY_RESEARCH_INSTRUCTIONS,
    CompanyResearchCampaign,
    build_company_research_inputs,
    build_company_research_task,
)
from backend.app.agents.company_research_runtime import CompanyResearchRuntime
from backend.app.agents.application_draft import (
    APPLICATION_DRAFT_INSTRUCTIONS,
    ApplicationDraftBrief,
    build_application_draft_inputs,
    build_application_draft_task,
    slugify,
)
from backend.app.agents.application_draft_runtime import ApplicationDraftRuntime
from backend.app.agents.onboarding_chat import OnboardingCodexChatAdapter
from backend.app.agents.onboarding_recruiter_prompt import (
    ONBOARDING_ARTIFACT_FILENAMES,
    build_onboarding_agent_instructions,
    build_onboarding_start_message,
)
from backend.app.agents.pi_rpc import PiRpcError, PiRpcOnboardingChatAdapter
from backend.app.agents.run_folder import RunFolderGenerator, RunFolderSpec, RunInputFile
from backend.app.core.config import Settings
from backend.app.core.config import get_settings
from backend.app.db.models import (
    AuditLog,
    Company,
    Contact,
    EmailDraft,
    FitEvaluation,
    GmailConnection,
    ImportedFile,
    ImportedGateResult,
    MasterCvProfileSnapshot,
    OnboardingSession,
    OutreachRecord,
    PolicySnapshot,
    SendApprovalSnapshot,
    Run,
    SendIntent,
    SendReservation,
    SentMessage,
    UserProfileSnapshot,
    ValidationResult,
    utc_now,
)
from backend.app.email_delivery import OutreachResolutionError, OutreachResolutionService, SendBatchService
from backend.app.email_delivery.adapters import local_file_gmail_credentials_available
from backend.app.db.session import get_session
from backend.app.db.normalization import normalize_recipient_email
from backend.app.gates.evaluate_only import EvaluateOnlyGateService
from backend.app.imports.file_classifier import classify_filename
from backend.app.imports.import_service import (
    APPLICATION_DRAFT_FILENAMES,
    APPLICATION_DRAFT_RUN_TYPE,
    COMPANY_RESEARCH_FILENAMES,
    ONBOARDING_CHAT_FILENAMES,
    RunImportService,
)
from backend.app.onboarding.promotion import OnboardingPromotionService, SnapshotPromotionRequest
from backend.app.schemas.api import (
    AuditLogResponse,
    ApplicationDraftImportResponse,
    ApplicationDraftBatchRequest,
    ApplicationDraftBatchResponse,
    ApplicationDraftBatchItemResponse,
    ApplicationDraftLaunchResponse,
    ApplicationDraftRequest,
    ApplicationDraftResponse,
    ApplicationDraftStatusResponse,
    CompanyResearchCampaignRequest,
    CompanyResearchCampaignResponse,
    CompanyResearchImportResponse,
    CompanyResearchLaunchResponse,
    CompanyResearchStatusResponse,
    CompanyResponse,
    ContactResponse,
    DashboardSummaryResponse,
    EmailDraftResponse,
    EmailDeliverySettingsResponse,
    FitEvaluationResponse,
    GateEvaluationResponse,
    GateResultResponse,
    GateResultSummaryResponse,
    HealthResponse,
    ImportedFileResponse,
    ImportResponse,
    ImportSummaryItem,
    OnboardingArtifactImportResponse,
    OnboardingArtifactContentResponse,
    OnboardingArtifactResponse,
    OnboardingArtifactsResponse,
    OnboardingChatEntryResponse,
    OnboardingChatActionResponse,
    OnboardingChatFinishResponse,
    OnboardingChatMessageRequest,
    OnboardingChatMessageResponse,
    OnboardingInputFileResponse,
    OnboardingInputFilesResponse,
    OnboardingSessionStateResponse,
    OnboardingChatStartResponse,
    OnboardingTerminalLaunchResponse,
    OnboardingPromotionRequest,
    OnboardingPromotionResponse,
    OnboardingSnapshotResponse,
    OutboxAttachmentLink,
    OutboxDraftResponse,
    OutboxSendAllRequest,
    OutboxSendAllResponse,
    OutboxSentResponse,
    ProfileSnapshotSummaryResponse,
    ProfileSummaryResponse,
    QueueDraftForSendRequest,
    QueueDraftForSendResponse,
    OutreachRecordResponse,
    RunDetailResponse,
    RunResponse,
    SendIntentResponse,
    SendBatchItemResponse,
    SendBatchRequest,
    SendBatchResponse,
    SentMessageResponse,
    OutreachResolutionRequest,
    OutreachResolutionResponse,
    ValidationResultResponse,
)
from backend.app.send_intents import DraftQueueError, DraftSendIntentQueueService

router = APIRouter()
ONBOARDING_RUNTIME_ERRORS = (TmuxCodexError, PiRpcError)
APPLICATION_DRAFT_BATCH_TERMINAL_STATUSES = {"imported", "imported_with_errors", "import_failed", "application_draft_failed", "failed"}
_APPLICATION_DRAFT_BATCHES: dict[str, dict[str, Any]] = {}
_APPLICATION_DRAFT_BATCH_LOCK = threading.Lock()


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


def _safe_input_filename(filename: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_. -]+", "-", filename).strip(" .-")
    if not cleaned or cleaned in {".", ".."}:
        raise HTTPException(status_code=400, detail="Invalid input filename")
    allowed_suffixes = {".pdf", ".doc", ".docx", ".txt", ".md", ".json"}
    if not any(cleaned.lower().endswith(suffix) for suffix in allowed_suffixes):
        raise HTTPException(status_code=400, detail="Unsupported input file type")
    return cleaned[:160]


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


def _import_response(result: Any) -> ImportResponse:
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


def _chat_entry_response(entry: dict[str, object]) -> OnboardingChatEntryResponse:
    content = str(entry.get("content") or "")
    event = entry.get("event") if isinstance(entry.get("event"), str) else None
    if _is_internal_onboarding_prompt(content):
        content = _internal_onboarding_prompt_label(content)
        event = event or "internal_prompt_redacted"
    return OnboardingChatEntryResponse(
        run_id=str(entry.get("run_id") or ""),
        role=str(entry.get("role") or ""),
        content=content,
        created_at=str(entry.get("created_at") or ""),
        raw_capture=entry.get("raw_capture") if isinstance(entry.get("raw_capture"), str) else None,
        event=event,
    )


def _chat_entries_response(entries: list[dict[str, object]]) -> list[OnboardingChatEntryResponse]:
    return [_chat_entry_response(entry) for entry in entries]


def _is_internal_onboarding_prompt(content: str) -> bool:
    return content.startswith("Finalize this onboarding interview.") or "Validation failures JSON:" in content


def _internal_onboarding_prompt_label(content: str) -> str:
    if content.startswith("Finalize this onboarding interview."):
        return "Finish artifacts"
    if "Validation failures JSON:" in content:
        return "Repair artifacts"
    return "Internal onboarding action"


def _session_state_response(
    run_id: str,
    adapter: OnboardingCodexChatAdapter,
    entries: list[dict[str, object]] | None = None,
) -> OnboardingSessionStateResponse:
    raw_entries = adapter.transcript_entries(run_id) if entries is None else entries
    if hasattr(adapter, "session_state"):
        state = adapter.session_state(run_id)
        return OnboardingSessionStateResponse(
            run_id=state.run_id,
            status=state.status,
            updated_at=state.updated_at,
            tmux=state.tmux,
            last_error=state.last_error,
            entries=_chat_entries_response(raw_entries),
        )
    return OnboardingSessionStateResponse(
        run_id=run_id,
        status="not_started" if not raw_entries else "running",
        updated_at="",
        entries=_chat_entries_response(raw_entries),
    )


def _persist_onboarding_session(
    session: Session,
    run_id: str,
    state: OnboardingSessionStateResponse,
    entries: list[OnboardingChatEntryResponse],
) -> None:
    record = session.exec(select(OnboardingSession).where(OnboardingSession.session_id == run_id)).first()
    if record is None:
        record = OnboardingSession(session_id=run_id, run_id=run_id)
    record.status = state.status
    record.transport = "tmux" if state.tmux else "pi_rpc"
    record.transport_metadata_json = json.dumps(state.model_dump(mode="json"), sort_keys=True)
    record.transcript_json = json.dumps([entry.model_dump(mode="json") for entry in entries], sort_keys=True)
    record.started_at = record.started_at or (utc_now() if state.status not in {"not_started", "failed"} else None)
    if state.status in {"closed", "completed"}:
        record.completed_at = utc_now()
    record.updated_at = utc_now()
    session.add(record)
    session.commit()


def get_onboarding_chat_adapter(settings: Settings = Depends(get_settings)) -> OnboardingCodexChatAdapter:
    if settings.onboarding_chat_runtime == "pi_rpc":
        return PiRpcOnboardingChatAdapter(settings=settings)
    if settings.onboarding_chat_runtime != "tmux":
        raise HTTPException(status_code=500, detail=f"Unsupported onboarding chat runtime: {settings.onboarding_chat_runtime}")
    target = TmuxTarget(
        distro=settings.codex_wsl_distro,
        session=settings.codex_tmux_session,
        window=settings.codex_tmux_window,
        pane=settings.codex_tmux_pane,
    )
    return OnboardingCodexChatAdapter(
        TmuxCodexBridge(target),
        workdir=settings.codex_workdir,
        runs_root=scoped_runs_root(settings.runs_root),
        reply_wait_seconds=settings.codex_chat_reply_wait_seconds,
    )


def get_company_research_runtime(settings: Settings = Depends(get_settings)) -> CompanyResearchRuntime:
    return CompanyResearchRuntime(settings=settings)


def get_application_draft_runtime(settings: Settings = Depends(get_settings)) -> ApplicationDraftRuntime:
    return ApplicationDraftRuntime(settings=settings)


def _onboarding_finalization_prompt(run_id: str) -> str:
    artifact_list = ", ".join(f"`../output/{filename}`" for filename in ONBOARDING_ARTIFACT_FILENAMES)
    schema_bundle = _onboarding_schema_bundle()
    return (
        "Finalize this onboarding interview. Create the directory "
        f"`../output` if needed and write candidate artifacts for onboarding run `{run_id}`: {artifact_list}. "
        "Each JSON file must conform exactly to its matching JSON Schema. The complete schemas are included below; "
        "do not guess alternate field names. "
        "Use only facts stated by the user in this chat or backed by local input files; clearly mark "
        "uncertain, inferred, or incomplete fields with needs_review provenance and/or "
        "`onboarding_review.json` items. Keep all artifacts candidate/unapproved. "
        "Do not create outreach, gate, reservation, or sending state. After writing the files, "
        "reply briefly with the paths written and any review caveats.\n\n"
        "JSON Schemas:\n"
        f"{schema_bundle}"
    )


def _onboarding_schema_bundle() -> str:
    bundled: dict[str, Any] = {}
    for filename in ONBOARDING_ARTIFACT_FILENAMES:
        schema_name = filename.replace(".json", ".schema.json")
        schema_path = get_settings().schemas_root / schema_name
        bundled[schema_name] = json.loads(schema_path.read_text(encoding="utf-8"))
    return json.dumps(bundled, ensure_ascii=False, indent=2)


def _onboarding_validation_failures(import_result: Any) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for result in import_result.validation_results:
        if result.status == "schema_validation_passed":
            continue
        failures.append(
            {
                "filename": result.filename,
                "status": result.status,
                "schema_name": result.schema_name,
                "error_count": result.error_count,
                "reason_codes": _json_loads(result.reason_codes_json, []),
                "errors": _json_loads(result.errors_json, []),
            }
        )
    return failures


def _onboarding_artifact_repair_prompt(run_id: str, failures: list[dict[str, Any]], attempt: int, max_attempts: int) -> str:
    schema_bundle = _onboarding_schema_bundle()
    return (
        f"Attempt {attempt}/{max_attempts}: backend schema validation failed for onboarding run `{run_id}`.\n\n"
        "Repair the candidate artifact files using only the allowed onboarding artifact write tool. "
        "Rewrite complete JSON documents, not patches. Do not create any files except "
        "`user_profile.json`, `master_cv_profile.json`, `policy.json`, and `onboarding_review.json` under `../output`. "
        "The complete JSON Schemas are included below; conform to them exactly and do not guess alternate field names. "
        "Do not invent facts to satisfy required fields; use `needs_review` provenance or review items where evidence is missing. "
        "After rewriting, reply briefly with what you changed.\n\n"
        "JSON Schemas:\n"
        f"{schema_bundle}\n\n"
        "Validation failures JSON:\n"
        f"{json.dumps(failures, ensure_ascii=False, indent=2)}"
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


def _drafted_company_ids(session: Session) -> set[str]:
    values = session.exec(select(EmailDraft.external_company_id)).all()
    return {value for value in values if value}


CONTACTED_OUTREACH_STATUSES = {"sent", "provider_accepted", "outcome_uncertain"}


def _latest_company_send_intent(session: Session, company: Company) -> SendIntent | None:
    return session.exec(
        select(SendIntent)
        .where(SendIntent.external_company_id == company.company_id)
        .order_by(SendIntent.created_at.desc(), SendIntent.id.desc())
    ).first()


def _latest_company_outreach(session: Session, company: Company) -> OutreachRecord | None:
    return session.exec(
        select(OutreachRecord)
        .where(
            (OutreachRecord.company_id == company.id)
            | (OutreachRecord.company_policy_key == company.company_policy_key)
        )
        .where(OutreachRecord.status.in_(CONTACTED_OUTREACH_STATUSES))
        .order_by(OutreachRecord.occurred_at.desc(), OutreachRecord.id.desc())
    ).first()


def _latest_company_fit(session: Session, company: Company) -> FitEvaluation | None:
    return session.exec(
        select(FitEvaluation)
        .where(
            (FitEvaluation.company_id == company.id)
            | (FitEvaluation.external_company_id == company.company_id)
        )
        .order_by(FitEvaluation.created_at.desc(), FitEvaluation.id.desc())
    ).first()


def _company_response(
    company: Company,
    *,
    session: Session,
    drafted_company_ids: set[str] | None = None,
    active_profile_company_ids: set[int] | None = None,
) -> CompanyResponse:
    send_intent = _latest_company_send_intent(session, company)
    latest_gate = _latest_gate_result(session, send_intent.intent_id) if send_intent is not None else None
    outreach = _latest_company_outreach(session, company)
    fit = _latest_company_fit(session, company)
    is_active_profile_scope = company.id in (active_profile_company_ids or set())
    has_application_draft = company.company_id in (drafted_company_ids or set())
    has_policy_conflicts = _json_has_items(company.policy_conflicts_json)
    can_draft_application = not has_application_draft and not has_policy_conflicts
    block_reason = None
    if has_application_draft:
        block_reason = "draft_already_exists"
    elif has_policy_conflicts:
        block_reason = "policy_conflict_present"
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
        is_active_profile_scope=is_active_profile_scope,
        can_draft_application=can_draft_application,
        application_draft_block_reason=block_reason,
        has_application_draft=has_application_draft,
        has_send_intent=send_intent is not None,
        send_intent_status=send_intent.status if send_intent is not None else None,
        send_gate_status=latest_gate.status if latest_gate is not None else None,
        has_been_contacted=outreach is not None,
        outreach_status=outreach.status if outreach is not None else None,
        fit_score=fit.fit_score if fit is not None else None,
        fit_decision=fit.decision if fit is not None else None,
        fit_reasons=_json_loads(fit.reasons_json, []) if fit is not None else [],
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


def _email_draft_response(draft: EmailDraft, session: Session | None = None) -> EmailDraftResponse:
    queued_intent = (
        session.exec(select(SendIntent).where(SendIntent.external_email_draft_id == draft.draft_id)).first()
        if session is not None
        else None
    )
    queued_gate = _latest_gate_result(session, queued_intent.intent_id) if session is not None and queued_intent is not None else None
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
        queued_send_intent_id=queued_intent.intent_id if queued_intent is not None else None,
        queued_gate_status=queued_gate.status if queued_gate is not None else None,
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


def _provider_url(message: SentMessage) -> str | None:
    if message.provider != "gmail":
        return None
    identifier = message.provider_thread_id or message.provider_message_id
    if not identifier:
        return None
    return f"https://mail.google.com/mail/u/0/#all/{identifier}"


def _sent_message_response(message: SentMessage, session: Session) -> SentMessageResponse:
    approval = session.get(SendApprovalSnapshot, message.approval_snapshot_id) if message.approval_snapshot_id is not None else None
    intent = session.get(SendIntent, message.send_intent_id) if message.send_intent_id is not None else None
    attachments = _json_loads(approval.attachments_json, []) if approval is not None else []
    return SentMessageResponse(
        id=message.id or 0,
        sent_message_id=message.sent_message_id,
        approval_id=approval.approval_id if approval is not None else None,
        send_intent_id=message.send_intent_id,
        external_intent_id=intent.intent_id if intent is not None else None,
        external_company_id=intent.external_company_id if intent is not None else None,
        external_contact_id=intent.external_contact_id if intent is not None else None,
        external_email_draft_id=intent.external_email_draft_id if intent is not None else None,
        provider=message.provider,
        provider_message_id=message.provider_message_id,
        provider_thread_id=message.provider_thread_id,
        provider_url=_provider_url(message),
        status=message.status,
        normalized_recipient_email=message.normalized_recipient_email,
        company_policy_key=message.company_policy_key,
        network_performed=message.network_performed,
        subject=approval.subject if approval is not None else None,
        body_text=approval.body_text if approval is not None else None,
        body_html=approval.body_html if approval is not None else None,
        attachments=attachments if isinstance(attachments, list) else [],
        provider_response=_json_loads(message.provider_response_json, {}),
        error=_json_loads(message.error_json, {}),
        created_at=message.created_at,
        accepted_at=message.accepted_at,
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


OUTBOX_CONTACTED_STATUSES = {"sent", "provider_accepted", "outcome_uncertain", "contacted"}
OUTBOX_ACTIVE_RESERVATION_STATUSES = {"active", "reserved", "attempting_provider_send", "outcome_uncertain"}


def _company_for_draft(session: Session, draft: EmailDraft) -> Company | None:
    return session.get(Company, draft.company_id) if draft.company_id is not None else None


def _contact_for_draft(session: Session, draft: EmailDraft) -> Contact | None:
    return session.get(Contact, draft.contact_id) if draft.contact_id is not None else None


def _intent_for_draft(session: Session, draft: EmailDraft) -> SendIntent | None:
    return session.exec(select(SendIntent).where(SendIntent.external_email_draft_id == draft.draft_id)).first()


def _outbox_email_for_contact(contact: Contact | None) -> tuple[str | None, str | None]:
    email = (contact.raw_email if contact is not None else "") or ""
    if not email.strip():
        return None, "missing_email"
    try:
        return normalize_recipient_email(email), None
    except ValueError:
        return email.strip(), "invalid_email"


def _outbox_cv_link(draft: EmailDraft) -> OutboxAttachmentLink | None:
    attachments = _json_loads(draft.attachments_json, [])
    if not isinstance(attachments, list):
        return None
    for attachment in attachments:
        if not isinstance(attachment, dict):
            continue
        attachment_id = attachment.get("attachment_id")
        path = str(attachment.get("path") or "")
        kind = attachment.get("kind")
        if not attachment_id:
            continue
        if kind == "cv" or path.lower().endswith(".pdf"):
            return OutboxAttachmentLink(
                attachment_id=str(attachment_id),
                label="Open PDF",
                url=f"/application-drafts/{draft.draft_id}/attachments/{attachment_id}",
                kind=str(kind) if kind is not None else None,
            )
    return None


def _outbox_attachment_exists(session: Session, draft: EmailDraft, link: OutboxAttachmentLink | None) -> bool:
    if link is None:
        return False
    imported_file = session.get(ImportedFile, draft.imported_file_id) if draft.imported_file_id is not None else None
    if imported_file is None:
        return False
    run = session.exec(select(Run).where(Run.run_id == imported_file.run_id)).first()
    output_root = Path(run.output_path).resolve() if run is not None else Path(imported_file.path).resolve().parent
    attachments = _json_loads(draft.attachments_json, [])
    if not isinstance(attachments, list):
        return False
    attachment = next(
        (item for item in attachments if isinstance(item, dict) and item.get("attachment_id") == link.attachment_id),
        None,
    )
    if attachment is None:
        return False
    path_value = attachment.get("path")
    if not isinstance(path_value, str) or not path_value:
        return False
    relative_path = Path(path_value.replace("\\", "/"))
    if relative_path.is_absolute():
        return False
    if relative_path.parts and relative_path.parts[0] == "output":
        relative_path = Path(*relative_path.parts[1:])
    return (output_root / relative_path).resolve().is_file()


def _outbox_has_contacted_record(
    session: Session,
    *,
    company: Company | None,
    normalized_email: str | None,
) -> bool:
    if normalized_email:
        recipient_record = session.exec(
            select(OutreachRecord).where(
                OutreachRecord.normalized_recipient_email == normalized_email,
                OutreachRecord.dedupe_recipient == True,  # noqa: E712
                OutreachRecord.status.in_(OUTBOX_CONTACTED_STATUSES),
            )
        ).first()
        if recipient_record is not None:
            return True
    if company is not None:
        company_record = session.exec(
            select(OutreachRecord).where(
                OutreachRecord.company_policy_key == company.company_policy_key,
                OutreachRecord.dedupe_company == True,  # noqa: E712
                OutreachRecord.status.in_(OUTBOX_CONTACTED_STATUSES),
            )
        ).first()
        if company_record is not None:
            return True
    return False


def _outbox_has_active_reservation(
    session: Session,
    *,
    company: Company | None,
    normalized_email: str | None,
) -> bool:
    if normalized_email:
        recipient_reservation = session.exec(
            select(SendReservation).where(
                SendReservation.normalized_recipient_email == normalized_email,
                SendReservation.dedupe_recipient == True,  # noqa: E712
                SendReservation.status.in_(OUTBOX_ACTIVE_RESERVATION_STATUSES),
            )
        ).first()
        if recipient_reservation is not None:
            return True
    if company is not None:
        company_reservation = session.exec(
            select(SendReservation).where(
                SendReservation.company_policy_key == company.company_policy_key,
                SendReservation.dedupe_company == True,  # noqa: E712
                SendReservation.status.in_(OUTBOX_ACTIVE_RESERVATION_STATUSES),
            )
        ).first()
        if company_reservation is not None:
            return True
    return False


def _outbox_draft_status(
    session: Session,
    *,
    draft: EmailDraft,
    company: Company | None,
    contact: Contact | None,
    normalized_email: str | None,
    email_error: str | None,
    cv: OutboxAttachmentLink | None,
    intent: SendIntent | None,
) -> tuple[str, str, str | None]:
    if intent is not None and intent.status == "sent":
        return "sent", "Sent", None
    if email_error == "missing_email":
        return "blocked", "Missing email", "missing_email"
    if email_error == "invalid_email":
        return "blocked", "Invalid email", "invalid_email"
    if not draft.body_text.strip():
        return "blocked", "Missing body", "missing_body"
    if cv is None or not _outbox_attachment_exists(session, draft, cv):
        return "blocked", "Missing CV", "missing_cv"
    if _outbox_has_contacted_record(session, company=company, normalized_email=normalized_email) or _outbox_has_active_reservation(
        session,
        company=company,
        normalized_email=normalized_email,
    ):
        return "blocked", "Already contacted", "already_contacted"
    return "ready", "Ready", None


def _outbox_draft_response(draft: EmailDraft, session: Session) -> OutboxDraftResponse:
    company = _company_for_draft(session, draft)
    contact = _contact_for_draft(session, draft)
    intent = _intent_for_draft(session, draft)
    email, email_error = _outbox_email_for_contact(contact)
    cv = _outbox_cv_link(draft)
    status, label, blocker = _outbox_draft_status(
        session,
        draft=draft,
        company=company,
        contact=contact,
        normalized_email=email if email_error is None else None,
        email_error=email_error,
        cv=cv,
        intent=intent,
    )
    return OutboxDraftResponse(
        draft_id=draft.draft_id,
        intent_id=intent.intent_id if intent is not None else None,
        company_id=draft.external_company_id,
        company_name=company.name if company is not None else draft.external_company_id,
        email_address=email,
        drafted_at=draft.created_at,
        status=status,
        status_label=label,
        blocker_code=blocker,
        subject=draft.subject,
        body_text=draft.body_text,
        email_url=f"/email-drafts/{draft.draft_id}",
        cv=cv,
    )


def _outbox_sent_response(message: SentMessage, session: Session) -> OutboxSentResponse:
    approval = session.get(SendApprovalSnapshot, message.approval_snapshot_id) if message.approval_snapshot_id is not None else None
    intent = session.get(SendIntent, message.send_intent_id) if message.send_intent_id is not None else None
    company = session.get(Company, intent.company_id) if intent is not None and intent.company_id is not None else None
    attachments = _json_loads(approval.attachments_json, []) if approval is not None else []
    cv = None
    if intent is not None and intent.external_email_draft_id:
        for attachment in attachments if isinstance(attachments, list) else []:
            if not isinstance(attachment, dict):
                continue
            attachment_id = attachment.get("attachment_id")
            path = str(attachment.get("path") or "")
            kind = attachment.get("kind")
            if attachment_id and (kind == "cv" or path.lower().endswith(".pdf")):
                cv = OutboxAttachmentLink(
                    attachment_id=str(attachment_id),
                    label="CV PDF",
                    url=f"/application-drafts/{intent.external_email_draft_id}/attachments/{attachment_id}",
                    kind=str(kind) if kind is not None else None,
                )
                break
    return OutboxSentResponse(
        sent_message_id=message.sent_message_id,
        company_id=intent.external_company_id if intent is not None else None,
        company_name=company.name if company is not None else (intent.external_company_id if intent is not None else message.company_policy_key),
        email_address=message.normalized_recipient_email,
        sent_at=message.accepted_at or message.created_at,
        status=message.status,
        subject=approval.subject if approval is not None else None,
        body_text=approval.body_text if approval is not None else None,
        email_url=f"/sent-messages/{message.sent_message_id}",
        cv=cv,
        provider_url=_provider_url(message),
    )


def _onboarding_snapshot_responses(session: Session, run_id: str) -> list[OnboardingSnapshotResponse]:
    imported_file_ids = _imported_file_ids_for_run(session, run_id)
    if not imported_file_ids:
        return []
    snapshots: list[OnboardingSnapshotResponse] = []
    for snapshot_type, model, external_attr in (
        ("user_profile", UserProfileSnapshot, "profile_id"),
        ("master_cv_profile", MasterCvProfileSnapshot, "profile_id"),
        ("policy", PolicySnapshot, "policy_id"),
    ):
        for snapshot in session.exec(select(model).where(col(model.imported_file_id).in_(imported_file_ids))).all():
            snapshots.append(
                OnboardingSnapshotResponse(
                    snapshot_type=snapshot_type,
                    id=snapshot.id or 0,
                    external_id=getattr(snapshot, external_attr),
                    status=snapshot.status,
                )
            )
    return snapshots


def _snapshot_for_imported_file(session: Session, imported_file: ImportedFile | None) -> tuple[str | None, Any | None]:
    if imported_file is None or imported_file.id is None:
        return None, None
    for snapshot_type, model in (
        ("user_profile", UserProfileSnapshot),
        ("master_cv_profile", MasterCvProfileSnapshot),
        ("policy", PolicySnapshot),
    ):
        snapshot = session.exec(select(model).where(model.imported_file_id == imported_file.id)).first()
        if snapshot is not None:
            return snapshot_type, snapshot
    return None, None


def _artifact_status_from_validation(
    *,
    exists: bool,
    validation_result: ValidationResult | None,
    snapshot: Any | None,
    filename: str,
) -> tuple[str, str]:
    if not exists:
        return "missing", "missing"
    if validation_result is None:
        return "candidate", "needs_validation"
    if validation_result.status != "schema_validation_passed":
        return "invalid", "validation_errors"
    if snapshot is not None:
        return "ready_for_review" if snapshot.status == "candidate" else snapshot.status, snapshot.status
    if filename == "onboarding_review.json":
        return "ready_for_review", "review_items_available"
    return "schema_validation_passed", "validated"


def _onboarding_artifact_responses(
    session: Session,
    run_id: str,
    settings: Settings,
) -> list[OnboardingArtifactResponse]:
    output_path = scoped_runs_root(settings.runs_root) / run_id / "output"
    validation_results = session.exec(
        select(ValidationResult).where(ValidationResult.run_id == run_id).order_by(ValidationResult.filename, ValidationResult.id.desc())
    ).all()
    latest_validation: dict[str, ValidationResult] = {}
    for result in validation_results:
        latest_validation.setdefault(result.filename, result)

    imported_files = {
        imported_file.filename: imported_file
        for imported_file in session.exec(select(ImportedFile).where(ImportedFile.run_id == run_id)).all()
    }

    artifacts: list[OnboardingArtifactResponse] = []
    for filename in ONBOARDING_CHAT_FILENAMES:
        artifact_path = output_path / filename
        validation_result = latest_validation.get(filename)
        imported_file = imported_files.get(filename)
        snapshot_type, snapshot = _snapshot_for_imported_file(session, imported_file)
        status, review_state = _artifact_status_from_validation(
            exists=artifact_path.exists(),
            validation_result=validation_result,
            snapshot=snapshot,
            filename=filename,
        )
        snapshot_external_id = None
        if isinstance(snapshot, PolicySnapshot):
            snapshot_external_id = snapshot.policy_id
        elif snapshot is not None:
            snapshot_external_id = snapshot.profile_id
        artifacts.append(
            OnboardingArtifactResponse(
                filename=filename,
                schema_name=validation_result.schema_name if validation_result is not None else classify_filename(filename),
                exists=artifact_path.exists(),
                status=status,
                review_state=review_state,
                path=str(artifact_path),
                error_count=validation_result.error_count if validation_result is not None else 0,
                reason_codes=(_json_loads(validation_result.reason_codes_json, []) if validation_result is not None else []),
                errors=(_json_loads(validation_result.errors_json, []) if validation_result is not None else []),
                snapshot_type=snapshot_type,
                snapshot_id=snapshot.id if snapshot is not None else None,
                snapshot_external_id=snapshot_external_id,
                snapshot_status=snapshot.status if snapshot is not None else None,
            )
        )
    return artifacts


def _onboarding_input_file_responses(run_id: str, settings: Settings) -> list[OnboardingInputFileResponse]:
    input_path = scoped_runs_root(settings.runs_root) / run_id / "input"
    if not input_path.exists():
        return []
    files: list[OnboardingInputFileResponse] = []
    for path in sorted(file_path for file_path in input_path.iterdir() if file_path.is_file()):
        files.append(OnboardingInputFileResponse(filename=path.name, path=str(path), size_bytes=path.stat().st_size))
    return files


def _profile_snapshot_summary(snapshot_type: str, snapshot: Any) -> ProfileSnapshotSummaryResponse:
    external_id = snapshot.policy_id if isinstance(snapshot, PolicySnapshot) else snapshot.profile_id
    return ProfileSnapshotSummaryResponse(
        snapshot_type=snapshot_type,
        id=snapshot.id or 0,
        external_id=external_id,
        status=snapshot.status,
        created_at=snapshot.imported_at,
    )


def _latest_snapshot(session: Session, model: type[Any], status: str) -> Any | None:
    return session.exec(
        select(model)
        .where(model.status == status)
        .order_by(model.imported_file_id.is_(None), model.imported_at.desc())
    ).first()


def _approved_profile_bundle(session: Session) -> tuple[UserProfileSnapshot, MasterCvProfileSnapshot, PolicySnapshot]:
    user_profile = _latest_snapshot(session, UserProfileSnapshot, "approved")
    master_cv = _latest_snapshot(session, MasterCvProfileSnapshot, "approved")
    policy = _latest_snapshot(session, PolicySnapshot, "approved")
    if user_profile is None or master_cv is None or policy is None:
        raise HTTPException(status_code=409, detail="This workflow requires approved user profile, master CV profile, and policy snapshots.")
    return user_profile, master_cv, policy


def _raw_json_object(snapshot: Any) -> dict[str, Any]:
    data = json.loads(snapshot.raw_json)
    if not isinstance(data, dict):
        raise HTTPException(status_code=500, detail="Approved snapshot payload is not a JSON object.")
    return data


def _profile_target_locations(user_profile: dict[str, Any]) -> list[str]:
    preferences = user_profile.get("preferences")
    if not isinstance(preferences, dict):
        return []
    values = preferences.get("target_locations")
    if not isinstance(values, list):
        return []
    locations: list[str] = []
    for item in values:
        if isinstance(item, dict) and isinstance(item.get("value"), str) and item["value"].strip():
            locations.append(item["value"].strip())
        elif isinstance(item, str) and item.strip():
            locations.append(item.strip())
    return locations


def _known_company_summaries(session: Session, user_profile: UserProfileSnapshot) -> list[dict[str, Any]]:
    evaluations = session.exec(
        select(FitEvaluation)
        .where(FitEvaluation.user_profile_snapshot_id == user_profile.id)
        .order_by(FitEvaluation.created_at.desc())
    ).all()
    company_ids = {evaluation.company_id for evaluation in evaluations if evaluation.company_id is not None}
    if not company_ids:
        return []
    companies = session.exec(select(Company).where(col(Company.id).in_(company_ids)).order_by(Company.normalized_name, Company.company_id)).all()
    summaries: list[dict[str, Any]] = []
    for company in companies:
        summaries.append(
            {
                "company_id": company.company_id,
                "name": company.name,
                "normalized_name": company.normalized_name,
                "domain": company.normalized_domain or company.raw_domain,
                "company_policy_key": company.company_policy_key,
                "company_policy_key_kind": company.company_policy_key_kind,
                "profile_id": user_profile.profile_id,
                "profile_snapshot_id": user_profile.id,
            }
        )
    return summaries


def _safe_campaign_run_id(value: str | None) -> str:
    if value is None or not value.strip():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        return f"company-research-{stamp}"
    run_id = value.strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}", run_id):
        raise HTTPException(status_code=400, detail="run_id must use only letters, numbers, dots, dashes, or underscores.")
    return run_id


def _safe_application_draft_run_id(value: str | None, company_slug: str) -> str:
    if value is None or not value.strip():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        return f"application-draft-{company_slug}-{stamp}"
    run_id = value.strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}", run_id):
        raise HTTPException(status_code=400, detail="run_id must use only letters, numbers, dots, dashes, or underscores.")
    return run_id


def _read_required_text(path: Any, description: str) -> str:
    resolved = Path(path)
    if not resolved.is_file():
        raise HTTPException(status_code=409, detail=f"Missing {description}: {resolved}")
    return resolved.read_text(encoding="utf-8")


def _selected_application_contact(session: Session, company: Company, contact_id: str | None) -> Contact | None:
    if contact_id:
        contact = session.exec(select(Contact).where(Contact.contact_id == contact_id)).first()
        if contact is None:
            raise _not_found("Contact")
        if contact.external_company_id != company.company_id and contact.company_id != company.id:
            raise HTTPException(status_code=409, detail="Selected contact does not belong to the selected company.")
        return contact
    contacts = session.exec(select(Contact).where(Contact.external_company_id == company.company_id)).all()
    if not contacts:
        return None
    return sorted(contacts, key=lambda item: (item.confidence, item.created_at), reverse=True)[0]


def _application_draft_contact_placeholder(company: Company, run_id: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "contact_id": f"contact-{run_id}",
        "company_id": company.company_id,
        "status": "missing_imported_contact",
        "instructions": (
            "No imported contact exists for this company. Research one public professional contact email and write "
            "output/contact_candidate.json with this contact_id before writing email_draft.json."
        ),
    }


def _latest_fit_for_company(session: Session, company: Company) -> FitEvaluation | None:
    return session.exec(
        select(FitEvaluation)
        .where(FitEvaluation.external_company_id == company.company_id)
        .order_by(FitEvaluation.created_at.desc())
    ).first()


def _active_profile_company_ids(session: Session, user_profile: UserProfileSnapshot) -> set[int]:
    return {
        company_id
        for company_id in session.exec(
            select(FitEvaluation.company_id).where(FitEvaluation.user_profile_snapshot_id == user_profile.id)
        ).all()
        if company_id is not None
    }


def _existing_draft_company_ids(session: Session) -> set[str]:
    return {
        company_id
        for company_id in session.exec(select(EmailDraft.external_company_id)).all()
        if company_id
    }


def _application_draft_batch_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"application-draft-batch-{stamp}-{uuid.uuid4().hex[:8]}"


def _batch_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "queued_count": sum(1 for item in items if item["status"] == "queued"),
        "launched_count": sum(1 for item in items if item["status"] in {"launched", "running"}),
        "completed_count": sum(1 for item in items if item["status"] == "completed"),
        "skipped_count": sum(1 for item in items if item["status"] == "skipped"),
        "failed_count": sum(1 for item in items if item["status"] == "failed"),
    }


def _application_draft_batch_response(batch: dict[str, Any]) -> ApplicationDraftBatchResponse:
    items = [ApplicationDraftBatchItemResponse(**item) for item in batch["items"]]
    counts = _batch_counts(batch["items"])
    active_count = counts["queued_count"] + counts["launched_count"]
    status = "completed" if active_count == 0 else batch["status"]
    return ApplicationDraftBatchResponse(
        batch_id=batch["batch_id"],
        status=status,
        mode=batch["mode"],
        concurrency=batch["concurrency"],
        requested_count=batch["requested_count"],
        status_endpoint=f"/application-drafts/batches/{batch['batch_id']}",
        items=items,
        **counts,
    )


def _count_by_status(session: Session, model: type[Any], status_column: Any) -> dict[str, int]:
    rows = session.exec(select(status_column, func.count(model.id)).group_by(status_column)).all()
    return {status: count for status, count in rows}


def _count(session: Session, model: type[Any]) -> int:
    return session.exec(select(func.count(model.id))).one()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", dry_run=get_settings().dry_run)


@router.get("/profile/summary", response_model=ProfileSummaryResponse)
def profile_summary(session: Session = Depends(get_session)) -> ProfileSummaryResponse:
    approved_user_profile = _latest_snapshot(session, UserProfileSnapshot, "approved")
    approved_master_cv = _latest_snapshot(session, MasterCvProfileSnapshot, "approved")
    approved_policy = _latest_snapshot(session, PolicySnapshot, "approved")
    candidate_user_profiles = session.exec(
        select(UserProfileSnapshot).where(UserProfileSnapshot.status == "candidate").order_by(UserProfileSnapshot.imported_at.desc())
    ).all()
    return ProfileSummaryResponse(
        has_approved_profile=approved_user_profile is not None,
        approved_user_profile=(
            _profile_snapshot_summary("user_profile", approved_user_profile) if approved_user_profile is not None else None
        ),
        candidate_user_profiles=[_profile_snapshot_summary("user_profile", snapshot) for snapshot in candidate_user_profiles],
        approved_master_cv_profile=(
            _profile_snapshot_summary("master_cv_profile", approved_master_cv) if approved_master_cv is not None else None
        ),
        approved_policy=_profile_snapshot_summary("policy", approved_policy) if approved_policy is not None else None,
    )


@router.post("/campaigns/company-research", response_model=CompanyResearchCampaignResponse)
def prepare_company_research_campaign(
    request: CompanyResearchCampaignRequest,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> CompanyResearchCampaignResponse:
    user_profile, master_cv, policy = _approved_profile_bundle(session)
    user_profile_payload = _raw_json_object(user_profile)
    target_locations = request.locations or _profile_target_locations(user_profile_payload)
    run_id = _safe_campaign_run_id(request.run_id)
    campaign = CompanyResearchCampaign(
        run_id=run_id,
        role_focus=request.role_focus,
        locations=target_locations,
        time_budget_minutes=request.time_budget_minutes,
        max_companies=request.max_companies,
        notes=request.notes,
    )
    existing_companies = _known_company_summaries(session, user_profile)
    input_payloads = build_company_research_inputs(
        user_profile=user_profile_payload,
        master_cv_profile=_raw_json_object(master_cv),
        policy=_raw_json_object(policy),
        company_schema=(settings.schemas_root / "company_candidate.schema.json").read_text(encoding="utf-8"),
        contact_schema=(settings.schemas_root / "contact_candidate.schema.json").read_text(encoding="utf-8"),
        fit_schema=(settings.schemas_root / "fit_evaluation.schema.json").read_text(encoding="utf-8"),
        campaign=campaign,
        existing_companies=existing_companies,
    )
    folder = RunFolderGenerator(settings=settings, session=session).prepare(
        RunFolderSpec(
            run_id=run_id,
            task=build_company_research_task(campaign),
            instructions=COMPANY_RESEARCH_INSTRUCTIONS,
            inputs=tuple(RunInputFile(path, content) for path, content in sorted(input_payloads.items())),
            expected_output_files=COMPANY_RESEARCH_FILENAMES,
            metadata={
                "task_type": "company_research",
                "profile_snapshot_id": user_profile.id,
                "master_cv_snapshot_id": master_cv.id,
                "policy_snapshot_id": policy.id,
                "existing_company_count": len(existing_companies),
                "target_company_count": request.max_companies,
            },
        )
    )
    run = session.exec(select(Run).where(Run.run_id == run_id)).first()
    if run is not None:
        run.agent_type = "company_research"
        session.add(run)
        session.commit()
    return CompanyResearchCampaignResponse(
        run_id=run_id,
        status="prepared",
        run_path=str(folder.path),
        input_path=str(folder.input_dir),
        output_path=str(folder.output_dir),
        prompt_path=str(folder.prompt_path),
        import_endpoint=f"/campaigns/company-research/{run_id}/import",
        expected_output_files=list(COMPANY_RESEARCH_FILENAMES),
        next_action="Launch company research to write batch JSON artifacts and import them after the Pi RPC process completes.",
    )


@router.post("/campaigns/company-research/{run_id}/launch", response_model=CompanyResearchLaunchResponse)
def launch_company_research_campaign(
    run_id: str,
    runtime: CompanyResearchRuntime = Depends(get_company_research_runtime),
) -> CompanyResearchLaunchResponse:
    try:
        result = runtime.launch(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return CompanyResearchLaunchResponse(
        run_id=result.run_id,
        status=result.status,
        runtime="pi_rpc",
        command=result.command,
        workdir=str(result.workdir),
        status_endpoint=f"/campaigns/company-research/{run_id}/status",
    )


@router.get("/campaigns/company-research/{run_id}/status", response_model=CompanyResearchStatusResponse)
def company_research_campaign_status(
    run_id: str,
    runtime: CompanyResearchRuntime = Depends(get_company_research_runtime),
) -> CompanyResearchStatusResponse:
    return CompanyResearchStatusResponse(**runtime.status(run_id))


@router.post("/campaigns/company-research/{run_id}/import", response_model=CompanyResearchImportResponse)
def import_company_research_campaign(
    run_id: str,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
    runtime: CompanyResearchRuntime = Depends(get_company_research_runtime),
) -> CompanyResearchImportResponse:
    result = RunImportService(session=session, settings=settings).import_run(run_id, run_type="company_research")
    return CompanyResearchImportResponse(
        run_id=run_id,
        import_result=_import_response(result),
        status=CompanyResearchStatusResponse(**runtime.status(run_id)),
    )


@router.post("/application-drafts", response_model=ApplicationDraftResponse)
def prepare_application_draft(
    request: ApplicationDraftRequest,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> ApplicationDraftResponse:
    return _prepare_application_draft_response(request, session=session, settings=settings)


def _prepare_application_draft_response(
    request: ApplicationDraftRequest,
    *,
    session: Session,
    settings: Settings,
) -> ApplicationDraftResponse:
    user_profile, master_cv, policy = _approved_profile_bundle(session)
    company = session.exec(select(Company).where(Company.company_id == request.company_id)).first()
    if company is None:
        raise _not_found("Company")
    fit_evaluation = _latest_fit_for_company(session, company)
    company_slug = slugify(company.name or company.company_id, fallback=company.company_id)
    run_id = _safe_application_draft_run_id(request.run_id, company_slug)
    contact = _selected_application_contact(session, company, request.contact_id)
    contact_needs_research = contact is None
    if contact_needs_research and not settings.application_draft_allow_contact_research:
        raise HTTPException(
            status_code=409,
            detail="Application drafts require an imported contact. Run contact research before drafting.",
        )
    selected_contact_id = contact.contact_id if contact is not None else f"contact-{run_id}"
    brief = ApplicationDraftBrief(
        run_id=run_id,
        draft_id=f"draft-{run_id}",
        company_id=company.company_id,
        contact_id=selected_contact_id,
        company_slug=company_slug,
        contact_needs_research=contact_needs_research,
        language=request.language,
        notes=request.notes,
    )
    handoff_docs: dict[str, str] = {}
    if settings.application_draft_include_handoff_docs:
        handoff_dir = settings.application_draft_handoff_dir
        handoff_docs = {
            "initiativbewerbung-style-guide.md": _read_required_text(
                handoff_dir / "initiativbewerbung-style-guide.md",
                "application draft style guide",
            ),
            "initiativbewerbung-workflow.md": _read_required_text(
                handoff_dir / "initiativbewerbung-workflow.md",
                "application draft workflow guide",
            ),
            "resume-job-search-context.md": _read_required_text(
                handoff_dir / "resume-job-search-context.md",
                "resume rendering context",
            ),
        }
    input_payloads = build_application_draft_inputs(
        brief=brief,
        user_profile=_raw_json_object(user_profile),
        master_cv_profile=_raw_json_object(master_cv),
        policy=_raw_json_object(policy),
        company=_json_loads(company.raw_json, {}),
        contact=_json_loads(contact.raw_json, {}) if contact is not None else _application_draft_contact_placeholder(company, run_id),
        fit_evaluation=_json_loads(fit_evaluation.raw_json, {}) if fit_evaluation is not None else None,
        email_draft_schema=(settings.schemas_root / "email_draft.schema.json").read_text(encoding="utf-8"),
        contact_schema=(settings.schemas_root / "contact_candidate.schema.json").read_text(encoding="utf-8"),
        master_cv_html=_read_required_text(settings.application_draft_master_cv_html_path, "master CV HTML"),
        handoff_docs=handoff_docs,
    )
    expected_json_outputs = APPLICATION_DRAFT_FILENAMES + (
        ("contact_candidate.json",) if contact_needs_research and settings.application_draft_allow_contact_research else ()
    )
    folder = RunFolderGenerator(settings=settings, session=session).prepare(
        RunFolderSpec(
            run_id=run_id,
            task=build_application_draft_task(brief),
            instructions=APPLICATION_DRAFT_INSTRUCTIONS,
            inputs=tuple(RunInputFile(path, content) for path, content in sorted(input_payloads.items())),
            expected_output_files=expected_json_outputs + (f"attachments/{brief.html_filename}", f"attachments/{brief.pdf_filename}"),
            metadata={
                "task_type": APPLICATION_DRAFT_RUN_TYPE,
                "profile_snapshot_id": user_profile.id,
                "master_cv_snapshot_id": master_cv.id,
                "policy_snapshot_id": policy.id,
                "company_id": company.company_id,
                "contact_id": selected_contact_id,
                "contact_needs_research": contact_needs_research,
                "draft_id": brief.draft_id,
            },
        )
    )
    (folder.output_dir / "attachments").mkdir(parents=True, exist_ok=True)
    run = session.exec(select(Run).where(Run.run_id == run_id)).first()
    if run is not None:
        run.agent_type = APPLICATION_DRAFT_RUN_TYPE
        session.add(run)
        session.commit()
    return ApplicationDraftResponse(
        run_id=run_id,
        status="prepared",
        company_id=company.company_id,
        contact_id=selected_contact_id,
        draft_id=brief.draft_id,
        run_path=str(folder.path),
        input_path=str(folder.input_dir),
        output_path=str(folder.output_dir),
        prompt_path=str(folder.prompt_path),
        launch_endpoint=f"/application-drafts/{run_id}/launch",
        import_endpoint=f"/application-drafts/{run_id}/import",
        status_endpoint=f"/application-drafts/{run_id}/status",
        expected_output_files=list(expected_json_outputs),
        expected_attachment_files=[f"attachments/{brief.html_filename}", f"attachments/{brief.pdf_filename}"],
        next_action=(
            "Launch the application draft agent to write a tailored CV PDF and email_draft.json, then import the draft "
            "for backend-controlled evaluation."
        ),
    )


def _company_ids_for_application_draft_batch(
    request: ApplicationDraftBatchRequest,
    *,
    session: Session,
    user_profile: UserProfileSnapshot,
) -> list[str]:
    if request.mode == "selected":
        return list(dict.fromkeys(request.company_ids))
    drafted_company_ids = _existing_draft_company_ids(session)
    companies = session.exec(select(Company).order_by(Company.created_at.desc(), Company.name)).all()
    return [company.company_id for company in companies if company.company_id not in drafted_company_ids]


def _prepare_application_draft_batch_items(
    request: ApplicationDraftBatchRequest,
    *,
    session: Session,
    settings: Settings,
    batch_id: str,
) -> list[dict[str, Any]]:
    user_profile, _master_cv, _policy = _approved_profile_bundle(session)
    drafted_company_ids = _existing_draft_company_ids(session)
    company_ids = _company_ids_for_application_draft_batch(request, session=session, user_profile=user_profile)
    items: list[dict[str, Any]] = []
    for index, company_id in enumerate(company_ids, start=1):
        company = session.exec(select(Company).where(Company.company_id == company_id)).first()
        if company is None:
            items.append({"company_id": company_id, "status": "skipped", "reason": "company_not_found"})
            continue
        if company.company_id in drafted_company_ids:
            items.append({"company_id": company_id, "status": "skipped", "reason": "draft_already_exists"})
            continue
        if _json_has_items(company.policy_conflicts_json):
            items.append({"company_id": company_id, "status": "skipped", "reason": "policy_conflict_present"})
            continue
        run_id = f"application-draft-{slugify(company.name or company.company_id, fallback=company.company_id)}-{batch_id[-15:]}-{index:03d}"
        try:
            prepared = _prepare_application_draft_response(
                ApplicationDraftRequest(
                    run_id=run_id[:120],
                    company_id=company.company_id,
                    language=request.language,
                    notes=request.notes,
                ),
                session=session,
                settings=settings,
            )
        except HTTPException as exc:
            reason = "needs_contact" if exc.status_code == 409 and "contact" in str(exc.detail).lower() else "prepare_failed"
            items.append({"company_id": company_id, "status": "skipped", "reason": reason, "detail": str(exc.detail)})
            continue
        items.append(
            {
                "company_id": company_id,
                "status": "queued",
                "run_id": prepared.run_id,
                "draft_id": prepared.draft_id,
                "contact_id": prepared.contact_id,
            }
        )
    return items


@router.post("/application-drafts/batches", response_model=ApplicationDraftBatchResponse)
def create_application_draft_batch(
    request: ApplicationDraftBatchRequest,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> ApplicationDraftBatchResponse:
    batch_id = _application_draft_batch_id()
    items = _prepare_application_draft_batch_items(request, session=session, settings=settings, batch_id=batch_id)
    batch = {
        "batch_id": batch_id,
        "status": "running" if any(item["status"] == "queued" for item in items) else "completed",
        "mode": request.mode,
        "concurrency": request.concurrency,
        "requested_count": len(request.company_ids) if request.mode == "selected" else len(items),
        "items": items,
    }
    with _APPLICATION_DRAFT_BATCH_LOCK:
        _APPLICATION_DRAFT_BATCHES[batch_id] = batch
    thread = threading.Thread(
        target=_run_application_draft_batch_scheduler,
        args=(batch_id, settings),
        daemon=True,
    )
    thread.start()
    return _application_draft_batch_response(batch)


@router.get("/application-drafts/batches/{batch_id}", response_model=ApplicationDraftBatchResponse)
def get_application_draft_batch(batch_id: str) -> ApplicationDraftBatchResponse:
    with _APPLICATION_DRAFT_BATCH_LOCK:
        batch = _APPLICATION_DRAFT_BATCHES.get(batch_id)
        if batch is None:
            raise _not_found("Application draft batch")
        snapshot = json.loads(json.dumps(batch))
    return _application_draft_batch_response(snapshot)


def _run_application_draft_batch_scheduler(batch_id: str, settings: Settings) -> None:
    runtime = ApplicationDraftRuntime(settings=settings)
    while True:
        with _APPLICATION_DRAFT_BATCH_LOCK:
            batch = _APPLICATION_DRAFT_BATCHES.get(batch_id)
            if batch is None:
                return
            items = batch["items"]
            running_items = [item for item in items if item["status"] in {"launched", "running"} and item.get("run_id")]
        for item in running_items:
            try:
                status = runtime.status(item["run_id"])
                status_value = status.get("status")
                with _APPLICATION_DRAFT_BATCH_LOCK:
                    item_ref = next((candidate for candidate in _APPLICATION_DRAFT_BATCHES[batch_id]["items"] if candidate is item), None)
                    if item_ref is None:
                        continue
                    if status_value in APPLICATION_DRAFT_BATCH_TERMINAL_STATUSES:
                        item_ref["status"] = "completed" if status_value == "imported" else "failed"
                        item_ref["reason"] = status_value if status_value != "imported" else None
                    else:
                        item_ref["status"] = "running"
            except Exception as exc:
                with _APPLICATION_DRAFT_BATCH_LOCK:
                    item["status"] = "failed"
                    item["reason"] = "status_failed"
                    item["detail"] = str(exc)
        with _APPLICATION_DRAFT_BATCH_LOCK:
            batch = _APPLICATION_DRAFT_BATCHES.get(batch_id)
            if batch is None:
                return
            running_count = sum(1 for item in batch["items"] if item["status"] in {"launched", "running"})
            launch_slots = max(0, int(batch["concurrency"]) - running_count)
            queued = [item for item in batch["items"] if item["status"] == "queued" and item.get("run_id")]
            to_launch = queued[:launch_slots]
        for item in to_launch:
            try:
                runtime.launch(item["run_id"])
                with _APPLICATION_DRAFT_BATCH_LOCK:
                    item["status"] = "launched"
            except Exception as exc:
                with _APPLICATION_DRAFT_BATCH_LOCK:
                    item["status"] = "failed"
                    item["reason"] = "launch_failed"
                    item["detail"] = str(exc)
        with _APPLICATION_DRAFT_BATCH_LOCK:
            batch = _APPLICATION_DRAFT_BATCHES.get(batch_id)
            if batch is None:
                return
            counts = _batch_counts(batch["items"])
            if counts["queued_count"] + counts["launched_count"] == 0:
                batch["status"] = "completed"
                return
        time.sleep(5)


@router.post("/application-drafts/{run_id}/launch", response_model=ApplicationDraftLaunchResponse)
def launch_application_draft(
    run_id: str,
    runtime: ApplicationDraftRuntime = Depends(get_application_draft_runtime),
) -> ApplicationDraftLaunchResponse:
    try:
        result = runtime.launch(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return ApplicationDraftLaunchResponse(
        run_id=result.run_id,
        status=result.status,
        runtime="pi_rpc",
        command=result.command,
        workdir=str(result.workdir),
        status_endpoint=f"/application-drafts/{run_id}/status",
    )


@router.get("/application-drafts/{run_id}/status", response_model=ApplicationDraftStatusResponse)
def application_draft_status(
    run_id: str,
    runtime: ApplicationDraftRuntime = Depends(get_application_draft_runtime),
) -> ApplicationDraftStatusResponse:
    return ApplicationDraftStatusResponse(**runtime.status(run_id))


@router.post("/application-drafts/{run_id}/import", response_model=ApplicationDraftImportResponse)
def import_application_draft(
    run_id: str,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
    runtime: ApplicationDraftRuntime = Depends(get_application_draft_runtime),
) -> ApplicationDraftImportResponse:
    result = RunImportService(session=session, settings=settings).import_run(run_id, run_type=APPLICATION_DRAFT_RUN_TYPE)
    return ApplicationDraftImportResponse(
        run_id=run_id,
        import_result=_import_response(result),
        status=ApplicationDraftStatusResponse(**runtime.status(run_id)),
    )


@router.post("/runs/{run_id}/import", response_model=ImportResponse)
def import_run(run_id: str, run_type: str | None = None, session: Session = Depends(get_session)) -> ImportResponse:
    result = RunImportService(session=session).import_run(run_id, run_type=run_type)
    return _import_response(result)


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


@router.get("/onboarding/chat/{run_id}/transcript", response_model=list[OnboardingChatEntryResponse])
def get_onboarding_chat_transcript(
    run_id: str,
    adapter: OnboardingCodexChatAdapter = Depends(get_onboarding_chat_adapter),
) -> list[OnboardingChatEntryResponse]:
    return _chat_entries_response(adapter.transcript_entries(run_id))


@router.get("/onboarding/chat/{run_id}/status", response_model=OnboardingSessionStateResponse)
def get_onboarding_chat_status(
    run_id: str,
    adapter: OnboardingCodexChatAdapter = Depends(get_onboarding_chat_adapter),
    session: Session = Depends(get_session),
) -> OnboardingSessionStateResponse:
    state = _session_state_response(run_id, adapter)
    _persist_onboarding_session(session, run_id, state, state.entries)
    return state


@router.post("/onboarding/chat/{run_id}/start", response_model=OnboardingChatStartResponse)
def start_onboarding_chat(
    run_id: str,
    adapter: OnboardingCodexChatAdapter = Depends(get_onboarding_chat_adapter),
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_session),
) -> OnboardingChatStartResponse:
    try:
        if hasattr(adapter, "prepare_agent_workspace"):
            adapter.prepare_agent_workspace(
                run_id,
                build_onboarding_agent_instructions(
                    run_id=run_id,
                    workdir=settings.codex_workdir,
                    runs_root=scoped_runs_root(settings.runs_root),
                    schemas_root=settings.schemas_root,
                ),
            )
        attachment = None
        if hasattr(adapter, "attach_session"):
            existing_state = adapter.session_state(run_id) if hasattr(adapter, "session_state") else None
            should_start_fresh = not bool(existing_state and existing_state.tmux)
            attachment = adapter.attach_session(run_id, fresh=should_start_fresh)
        status = adapter.start_or_attach(run_id)
        accepted = adapter.accept_trust_prompt_if_present()
        if hasattr(adapter, "ensure_recruiter_prompt"):
            adapter.ensure_recruiter_prompt(
                run_id,
                build_onboarding_start_message(run_id),
                force=bool(attachment and attachment.get("status") == "started"),
            )
    except ONBOARDING_RUNTIME_ERRORS as exc:
        if hasattr(adapter, "record_failure"):
            adapter.record_failure(run_id, str(exc))
        raise HTTPException(status_code=502, detail=f"Onboarding agent runtime unavailable: {exc}") from exc
    entries = adapter.transcript_entries(run_id)
    entry_responses = _chat_entries_response(entries)
    session_state = _session_state_response(run_id, adapter, entries)
    _persist_onboarding_session(session, run_id, session_state, entry_responses)
    return OnboardingChatStartResponse(
        run_id=run_id,
        status=status,
        trust_prompt_accepted=accepted,
        session_state=session_state,
        entries=entry_responses,
    )


@router.post("/onboarding/chat/{run_id}/messages", response_model=OnboardingChatMessageResponse)
def send_onboarding_chat_message(
    run_id: str,
    request: OnboardingChatMessageRequest,
    adapter: OnboardingCodexChatAdapter = Depends(get_onboarding_chat_adapter),
    session: Session = Depends(get_session),
) -> OnboardingChatMessageResponse:
    try:
        adapter.start_or_attach(run_id)
        adapter.accept_trust_prompt_if_present()
        reply = adapter.send_message(run_id, request.message)
    except ONBOARDING_RUNTIME_ERRORS as exc:
        if hasattr(adapter, "record_failure"):
            adapter.record_failure(run_id, str(exc))
        raise HTTPException(status_code=502, detail=f"Onboarding agent runtime unavailable: {exc}") from exc
    entries = adapter.transcript_entries(run_id)
    entry_responses = _chat_entries_response(entries)
    session_state = _session_state_response(run_id, adapter, entries)
    _persist_onboarding_session(session, run_id, session_state, entry_responses)
    return OnboardingChatMessageResponse(
        run_id=run_id,
        reply=reply.message,
        transcript_path=str(reply.transcript_path),
        session_state=session_state,
        entries=entry_responses,
    )


@router.post("/onboarding/chat/{run_id}/refresh", response_model=OnboardingChatMessageResponse)
def refresh_onboarding_chat_output(
    run_id: str,
    adapter: OnboardingCodexChatAdapter = Depends(get_onboarding_chat_adapter),
    session: Session = Depends(get_session),
) -> OnboardingChatMessageResponse:
    try:
        reply = adapter.refresh_output(run_id)
    except ONBOARDING_RUNTIME_ERRORS as exc:
        if hasattr(adapter, "record_failure"):
            adapter.record_failure(run_id, str(exc))
        raise HTTPException(status_code=502, detail=f"Onboarding agent runtime unavailable: {exc}") from exc
    entries = adapter.transcript_entries(run_id)
    entry_responses = _chat_entries_response(entries)
    session_state = _session_state_response(run_id, adapter, entries)
    _persist_onboarding_session(session, run_id, session_state, entry_responses)
    return OnboardingChatMessageResponse(
        run_id=run_id,
        reply=reply.message,
        transcript_path=str(reply.transcript_path),
        session_state=session_state,
        entries=entry_responses,
    )


@router.post("/onboarding/chat/{run_id}/close", response_model=OnboardingChatActionResponse)
def close_onboarding_chat(
    run_id: str,
    adapter: OnboardingCodexChatAdapter = Depends(get_onboarding_chat_adapter),
    session: Session = Depends(get_session),
) -> OnboardingChatActionResponse:
    try:
        adapter.close_session(run_id)
    except ONBOARDING_RUNTIME_ERRORS as exc:
        if hasattr(adapter, "record_failure"):
            adapter.record_failure(run_id, str(exc))
        raise HTTPException(status_code=502, detail=f"Onboarding agent runtime unavailable: {exc}") from exc
    entries = adapter.transcript_entries(run_id)
    entry_responses = _chat_entries_response(entries)
    session_state = _session_state_response(run_id, adapter, entries)
    _persist_onboarding_session(session, run_id, session_state, entry_responses)
    return OnboardingChatActionResponse(
        run_id=run_id,
        status="closed",
        session_state=session_state,
        entries=entry_responses,
    )


@router.post("/onboarding/chat/{run_id}/reset", response_model=OnboardingChatActionResponse)
def reset_onboarding_chat(
    run_id: str,
    adapter: OnboardingCodexChatAdapter = Depends(get_onboarding_chat_adapter),
    session: Session = Depends(get_session),
) -> OnboardingChatActionResponse:
    try:
        adapter.reset_session(run_id)
    except ONBOARDING_RUNTIME_ERRORS as exc:
        if hasattr(adapter, "record_failure"):
            adapter.record_failure(run_id, str(exc))
        raise HTTPException(status_code=502, detail=f"Onboarding agent runtime unavailable: {exc}") from exc
    entries = adapter.transcript_entries(run_id)
    entry_responses = _chat_entries_response(entries)
    session_state = _session_state_response(run_id, adapter, entries)
    _persist_onboarding_session(session, run_id, session_state, entry_responses)
    return OnboardingChatActionResponse(
        run_id=run_id,
        status="not_started",
        session_state=session_state,
        entries=entry_responses,
    )


@router.post("/onboarding/chat/{run_id}/open-terminal", response_model=OnboardingTerminalLaunchResponse)
def open_onboarding_tmux_terminal(
    run_id: str,
    adapter: OnboardingCodexChatAdapter = Depends(get_onboarding_chat_adapter),
) -> OnboardingTerminalLaunchResponse:
    try:
        command = adapter.open_terminal(run_id)
    except ONBOARDING_RUNTIME_ERRORS as exc:
        if hasattr(adapter, "record_failure"):
            adapter.record_failure(run_id, str(exc))
        raise HTTPException(status_code=502, detail=f"Onboarding agent terminal unavailable: {exc}") from exc
    return OnboardingTerminalLaunchResponse(
        run_id=run_id,
        status="opened",
        command=command,
        session_state=_session_state_response(run_id, adapter),
    )


@router.post("/onboarding/chat/{run_id}/finish", response_model=OnboardingChatFinishResponse)
def finish_onboarding_chat(
    run_id: str,
    adapter: OnboardingCodexChatAdapter = Depends(get_onboarding_chat_adapter),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> OnboardingChatFinishResponse:
    (scoped_runs_root(settings.runs_root) / run_id / "output").mkdir(parents=True, exist_ok=True)
    try:
        adapter.start_or_attach(run_id)
        adapter.accept_trust_prompt_if_present()
        reply = adapter.send_message(run_id, _onboarding_finalization_prompt(run_id))
    except ONBOARDING_RUNTIME_ERRORS as exc:
        raise HTTPException(status_code=502, detail=f"Onboarding agent runtime unavailable: {exc}") from exc

    import_service = RunImportService(session=session)
    import_result = import_service.import_run(run_id, run_type="onboarding_chat")
    repair_replies: list[str] = []
    max_repair_attempts = max(settings.onboarding_artifact_repair_attempts, 0)
    for attempt in range(1, max_repair_attempts + 1):
        failures = _onboarding_validation_failures(import_result)
        if not failures:
            break
        try:
            repair_reply = adapter.send_message(
                run_id,
                _onboarding_artifact_repair_prompt(run_id, failures, attempt, max_repair_attempts),
            )
        except ONBOARDING_RUNTIME_ERRORS as exc:
            raise HTTPException(status_code=502, detail=f"Onboarding agent artifact repair unavailable: {exc}") from exc
        repair_replies.append(repair_reply.message)
        import_result = import_service.import_run(run_id, run_type="onboarding_chat")

    if import_result.run.status == "imported":
        try:
            adapter.close_session(run_id)
        except ONBOARDING_RUNTIME_ERRORS:
            pass
    final_reply = reply.message
    if repair_replies:
        final_reply = "\n\n".join([reply.message, *repair_replies])
    final_entries = _chat_entries_response(adapter.transcript_entries(run_id))
    final_state = _session_state_response(run_id, adapter)
    _persist_onboarding_session(session, run_id, final_state, final_entries)
    return OnboardingChatFinishResponse(
        run_id=run_id,
        reply=final_reply,
        transcript_path=str(reply.transcript_path),
        import_result=_import_response(import_result),
        artifacts=_onboarding_artifact_responses(session, run_id, settings),
        entries=final_entries,
    )


@router.get("/onboarding/chat/{run_id}/artifacts", response_model=OnboardingArtifactsResponse)
def get_onboarding_artifacts(
    run_id: str,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> OnboardingArtifactsResponse:
    output_path = scoped_runs_root(settings.runs_root) / run_id / "output"
    return OnboardingArtifactsResponse(
        run_id=run_id,
        output_path=str(output_path),
        artifacts=_onboarding_artifact_responses(session, run_id, settings),
    )


@router.get("/onboarding/chat/{run_id}/artifacts/{filename}", response_model=OnboardingArtifactContentResponse)
def get_onboarding_artifact_content(
    run_id: str,
    filename: str,
    settings: Settings = Depends(get_settings),
) -> OnboardingArtifactContentResponse:
    if filename not in ONBOARDING_CHAT_FILENAMES:
        raise HTTPException(status_code=404, detail="Unknown onboarding artifact")
    output_path = (scoped_runs_root(settings.runs_root) / run_id / "output").resolve()
    artifact_path = (output_path / filename).resolve()
    if output_path not in artifact_path.parents:
        raise HTTPException(status_code=400, detail="Invalid artifact path")
    if not artifact_path.exists():
        return OnboardingArtifactContentResponse(
            run_id=run_id,
            filename=filename,
            path=str(artifact_path),
            exists=False,
        )
    raw_text = artifact_path.read_text(encoding="utf-8")
    parsed: dict[str, Any] | list[Any] | None = None
    try:
        loaded = json.loads(raw_text)
        if isinstance(loaded, (dict, list)):
            parsed = loaded
    except json.JSONDecodeError:
        parsed = None
    return OnboardingArtifactContentResponse(
        run_id=run_id,
        filename=filename,
        path=str(artifact_path),
        exists=True,
        raw_text=raw_text,
        json_content=parsed,
    )


@router.get("/onboarding/chat/{run_id}/input-files", response_model=OnboardingInputFilesResponse)
def list_onboarding_input_files(
    run_id: str,
    settings: Settings = Depends(get_settings),
) -> OnboardingInputFilesResponse:
    input_path = scoped_runs_root(settings.runs_root) / run_id / "input"
    return OnboardingInputFilesResponse(
        run_id=run_id,
        input_path=str(input_path),
        files=_onboarding_input_file_responses(run_id, settings),
    )


@router.put("/onboarding/chat/{run_id}/input-files/{filename}", response_model=OnboardingInputFileResponse)
async def upload_onboarding_input_file(
    run_id: str,
    filename: str,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> OnboardingInputFileResponse:
    safe_filename = _safe_input_filename(filename)
    content = await request.body()
    max_bytes = 20 * 1024 * 1024
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    if len(content) > max_bytes:
        raise HTTPException(status_code=413, detail="Uploaded file exceeds 20 MB")
    input_path = scoped_runs_root(settings.runs_root) / run_id / "input"
    input_path.mkdir(parents=True, exist_ok=True)
    destination = input_path / safe_filename
    destination.write_bytes(content)
    return OnboardingInputFileResponse(
        filename=destination.name,
        path=str(destination),
        size_bytes=destination.stat().st_size,
    )


@router.post("/onboarding/chat/{run_id}/import-artifacts", response_model=OnboardingArtifactImportResponse)
def import_onboarding_artifacts(
    run_id: str,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> OnboardingArtifactImportResponse:
    result = RunImportService(session=session, settings=settings).import_run(run_id, run_type="onboarding_chat")
    return OnboardingArtifactImportResponse(
        run_id=run_id,
        import_result=_import_response(result),
        artifacts=_onboarding_artifact_responses(session, run_id, settings),
    )


@router.get("/onboarding/runs/{run_id}/snapshots", response_model=list[OnboardingSnapshotResponse])
def list_onboarding_snapshots(run_id: str, session: Session = Depends(get_session)) -> list[OnboardingSnapshotResponse]:
    return _onboarding_snapshot_responses(session, run_id)


@router.post("/onboarding/runs/{run_id}/promote", response_model=OnboardingPromotionResponse)
def promote_onboarding_snapshots(
    run_id: str,
    request: OnboardingPromotionRequest,
    session: Session = Depends(get_session),
) -> OnboardingPromotionResponse:
    result = OnboardingPromotionService(session).promote_run_snapshots(
        run_id,
        SnapshotPromotionRequest(
            reviewer_id=request.reviewer_id,
            confirm_user_profile=request.confirm_user_profile,
            confirm_master_cv_profile=request.confirm_master_cv_profile,
            confirm_policy=request.confirm_policy,
        ),
    )
    session.commit()
    return OnboardingPromotionResponse(
        run_id=result.run_id,
        status=result.status,
        promoted=[OnboardingSnapshotResponse(**snapshot.as_dict()) for snapshot in result.promoted],
        issues=[issue.as_dict() for issue in result.issues],
    )


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
        send_approval_snapshots=_count(session, SendApprovalSnapshot),
        sent_messages=_count(session, SentMessage),
        send_intents_by_status=_count_by_status(session, SendIntent, SendIntent.status),
        gate_results_by_status=_count_by_status(session, ImportedGateResult, ImportedGateResult.status),
        outreach_records_by_status=_count_by_status(session, OutreachRecord, OutreachRecord.status),
    )


@router.get("/email-delivery/settings", response_model=EmailDeliverySettingsResponse)
def email_delivery_settings(
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_session),
) -> EmailDeliverySettingsResponse:
    identity = current_identity()
    local_file_credentials = local_file_gmail_credentials_available(settings)
    connection_source: str | None = None
    if identity is not None:
        database_connection = session.exec(
            select(GmailConnection).where(
                GmailConnection.user_id == identity.user_id,
                GmailConnection.status == "connected",
            )
        ).first()
        if database_connection is not None:
            gmail_configured = True
            connection_source = "database"
        else:
            gmail_configured = local_file_credentials
            connection_source = "local_file" if local_file_credentials else None
    else:
        gmail_configured = local_file_credentials
        connection_source = "local_file" if local_file_credentials else None
    if not settings.email_sending_enabled:
        mode = "disabled"
    elif settings.email_provider == "gmail_sandbox":
        mode = "gmail_sandbox"
    elif settings.email_provider == "gmail" and settings.email_allow_real_recipients:
        mode = "gmail_real_recipients"
    else:
        mode = "blocked_by_configuration"
    return EmailDeliverySettingsResponse(
        sending_enabled=settings.email_sending_enabled,
        provider=settings.email_provider,
        allow_real_recipients=settings.email_allow_real_recipients,
        sandbox_recipient=settings.gmail_sandbox_recipient,
        gmail_configured=gmail_configured,
        gmail_connection_available=bool(settings.google_oauth_client_id and settings.google_oauth_client_secret),
        gmail_connection_source=connection_source,
        mode=mode,
    )


@router.get("/companies", response_model=list[CompanyResponse])
def list_companies(
    run_id: str | None = None,
    min_confidence: float | None = Query(default=None, ge=0, le=1),
    has_review_flags: bool | None = None,
    has_policy_conflicts: bool | None = None,
    draft_status: str | None = Query(default=None, pattern="^(drafted|missing)$"),
    session: Session = Depends(get_session),
) -> list[CompanyResponse]:
    imported_file_ids = _imported_file_ids_for_run(session, run_id) if run_id is not None else None
    drafted_company_ids = _drafted_company_ids(session)
    user_profile = _latest_snapshot(session, UserProfileSnapshot, "approved")
    active_profile_company_ids = _active_profile_company_ids(session, user_profile) if user_profile is not None else set()
    companies = session.exec(select(Company).order_by(Company.created_at.desc(), Company.name)).all()
    return [
        _company_response(
            company,
            session=session,
            drafted_company_ids=drafted_company_ids,
            active_profile_company_ids=active_profile_company_ids,
        )
        for company in companies
        if _matches_import_run(company.imported_file_id, imported_file_ids)
        and (min_confidence is None or company.confidence >= min_confidence)
        and _matches_json_flag(company.review_flags_json, has_review_flags)
        and _matches_json_flag(company.policy_conflicts_json, has_policy_conflicts)
        and (draft_status is None or (company.company_id in drafted_company_ids) == (draft_status == "drafted"))
    ]


@router.get("/companies/{company_id}", response_model=CompanyResponse)
def get_company(company_id: str, session: Session = Depends(get_session)) -> CompanyResponse:
    company = session.exec(select(Company).where(Company.company_id == company_id)).first()
    if company is None:
        raise _not_found("Company")
    user_profile = _latest_snapshot(session, UserProfileSnapshot, "approved")
    active_profile_company_ids = _active_profile_company_ids(session, user_profile) if user_profile is not None else set()
    return _company_response(
        company,
        session=session,
        drafted_company_ids=_drafted_company_ids(session),
        active_profile_company_ids=active_profile_company_ids,
    )


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
        _email_draft_response(draft, session)
        for draft in drafts
        if _matches_import_run(draft.imported_file_id, imported_file_ids)
        and (company_id is None or draft.external_company_id == company_id)
        and (contact_id is None or draft.external_contact_id == contact_id)
        and (min_confidence is None or draft.confidence >= min_confidence)
        and _matches_json_flag(draft.review_flags_json, has_review_flags)
    ]


@router.get("/outbox/drafts", response_model=list[OutboxDraftResponse])
def list_outbox_drafts(session: Session = Depends(get_session)) -> list[OutboxDraftResponse]:
    drafts = session.exec(select(EmailDraft).order_by(EmailDraft.created_at.desc(), EmailDraft.draft_id)).all()
    return [_outbox_draft_response(draft, session) for draft in drafts]


@router.get("/outbox/sent", response_model=list[OutboxSentResponse])
def list_outbox_sent(session: Session = Depends(get_session)) -> list[OutboxSentResponse]:
    messages = session.exec(
        select(SentMessage)
        .join(SendApprovalSnapshot, SentMessage.approval_snapshot_id == SendApprovalSnapshot.id)
        .join(SendIntent, SentMessage.send_intent_id == SendIntent.id)
        .where(SentMessage.status == "provider_accepted")
        .where(SendApprovalSnapshot.email_draft_id.is_not(None))
        .where(~SendIntent.run_id.startswith("gmail-smoke-"))
        .order_by(SentMessage.created_at.desc(), SentMessage.sent_message_id)
    ).all()
    return [_outbox_sent_response(message, session) for message in messages]


def _send_batch_response(result: Any) -> SendBatchResponse:
    return SendBatchResponse(
        batch_id=result.batch_id,
        status=result.status,
        requested_count=result.requested_count,
        sent_count=result.sent_count,
        blocked_count=result.blocked_count,
        items=[
            SendBatchItemResponse(
                intent_id=item.intent_id,
                status=item.status,
                approval_id=item.approval_id,
                gate_result_id=item.gate_result_id,
                reservation_id=item.reservation_id,
                sent_message_id=item.sent_message_id,
                outreach_record_id=item.outreach_record_id,
                reason_codes=item.reason_codes,
                detail=item.detail,
            )
            for item in result.items
        ],
    )


@router.post("/outbox/send-all", response_model=OutboxSendAllResponse)
def outbox_send_all(
    request: OutboxSendAllRequest,
    session: Session = Depends(get_session),
) -> OutboxSendAllResponse:
    drafts = session.exec(select(EmailDraft).order_by(EmailDraft.created_at.desc(), EmailDraft.draft_id)).all()
    ready_rows = [row for row in (_outbox_draft_response(draft, session) for draft in drafts) if row.status == "ready"]
    intent_ids: list[str] = []
    queue_failed_count = 0
    for row in ready_rows:
        try:
            result = DraftSendIntentQueueService(session).queue_draft(row.draft_id, reviewer_id=request.reviewer_id)
        except DraftQueueError:
            queue_failed_count += 1
            continue
        intent_ids.append(result.send_intent.intent_id)
    batch_response = None
    if intent_ids:
        batch_response = _send_batch_response(SendBatchService(session=session).approve_and_send(intent_ids, request.reviewer_id))
    session.commit()
    refreshed_drafts = session.exec(select(EmailDraft).order_by(EmailDraft.created_at.desc(), EmailDraft.draft_id)).all()
    rows = [_outbox_draft_response(draft, session) for draft in refreshed_drafts]
    return OutboxSendAllResponse(
        requested_count=len(ready_rows),
        sent_count=batch_response.sent_count if batch_response is not None else 0,
        blocked_count=(batch_response.blocked_count if batch_response is not None else 0) + queue_failed_count,
        batch=batch_response,
        drafts=rows,
    )


@router.get("/email-drafts/{draft_id}", response_model=EmailDraftResponse)
def get_email_draft(draft_id: str, session: Session = Depends(get_session)) -> EmailDraftResponse:
    draft = session.exec(select(EmailDraft).where(EmailDraft.draft_id == draft_id)).first()
    if draft is None:
        raise _not_found("Email draft")
    return _email_draft_response(draft, session)


@router.post("/email-drafts/{draft_id}/queue-send", response_model=QueueDraftForSendResponse)
def queue_email_draft_for_send(
    draft_id: str,
    request: QueueDraftForSendRequest,
    session: Session = Depends(get_session),
) -> QueueDraftForSendResponse:
    try:
        result = DraftSendIntentQueueService(session).queue_draft(draft_id, reviewer_id=request.reviewer_id)
    except DraftQueueError as exc:
        status_code = 404 if exc.code == "draft_not_found" else 409
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    session.commit()
    session.refresh(result.send_intent)
    return QueueDraftForSendResponse(
        send_intent=_send_intent_response(result.send_intent, session),
        gate_result=GateResultSummaryResponse(
            gate_result_id=result.gate_evaluation.gate_result.gate_result_id,
            status=result.gate_evaluation.gate_result.status,
            evaluated_at=result.gate_evaluation.gate_result.evaluated_at,
            reasons=_json_loads(result.gate_evaluation.gate_result.reasons_json, []),
        ),
        created=result.created,
    )


@router.get("/application-drafts/{draft_id}/attachments/{attachment_id}")
def get_application_draft_attachment(
    draft_id: str,
    attachment_id: str,
    session: Session = Depends(get_session),
) -> FileResponse:
    draft = session.exec(select(EmailDraft).where(EmailDraft.draft_id == draft_id)).first()
    if draft is None:
        raise _not_found("Email draft")
    attachments = _json_loads(draft.attachments_json, [])
    attachment = next(
        (
            item
            for item in attachments
            if isinstance(item, dict) and item.get("attachment_id") == attachment_id
        ),
        None,
    )
    if attachment is None:
        raise _not_found("Attachment")
    attachment_path = attachment.get("path")
    if not isinstance(attachment_path, str) or not attachment_path:
        raise HTTPException(status_code=404, detail="Attachment path is missing.")
    imported_file = session.get(ImportedFile, draft.imported_file_id) if draft.imported_file_id is not None else None
    if imported_file is None:
        raise HTTPException(status_code=404, detail="Draft is not linked to an imported file.")
    run = session.exec(select(Run).where(Run.run_id == imported_file.run_id)).first()
    if run is None:
        raise _not_found("Run")
    output_root = Path(run.output_path).resolve()
    attachments_root = (output_root / "attachments").resolve()
    relative_path = Path(attachment_path.replace("\\", "/"))
    if relative_path.is_absolute():
        raise HTTPException(status_code=400, detail="Invalid attachment path.")
    if relative_path.parts and relative_path.parts[0] == "output":
        relative_path = Path(*relative_path.parts[1:])
    file_path = (output_root / relative_path).resolve()
    if file_path != attachments_root and attachments_root not in file_path.parents:
        raise HTTPException(status_code=400, detail="Invalid attachment path.")
    if not file_path.is_file():
        raise _not_found("Attachment file")
    suffix = file_path.suffix.lower()
    media_type = "application/pdf" if suffix == ".pdf" else "text/html" if suffix == ".html" else "application/octet-stream"
    return FileResponse(path=file_path, media_type=media_type, filename=file_path.name)


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


@router.get("/sent-messages", response_model=list[SentMessageResponse])
def list_sent_messages(
    run_id: str | None = None,
    company_id: str | None = None,
    contact_id: str | None = None,
    status: str | None = None,
    session: Session = Depends(get_session),
) -> list[SentMessageResponse]:
    messages = session.exec(select(SentMessage).order_by(SentMessage.created_at.desc(), SentMessage.sent_message_id)).all()
    responses: list[SentMessageResponse] = []
    for message in messages:
        intent = session.get(SendIntent, message.send_intent_id) if message.send_intent_id is not None else None
        if run_id is not None and (intent is None or intent.run_id != run_id):
            continue
        if company_id is not None and (intent is None or intent.external_company_id != company_id):
            continue
        if contact_id is not None and (intent is None or intent.external_contact_id != contact_id):
            continue
        if status is not None and message.status != status:
            continue
        responses.append(_sent_message_response(message, session))
    return responses


@router.get("/sent-messages/{sent_message_id}", response_model=SentMessageResponse)
def get_sent_message(sent_message_id: str, session: Session = Depends(get_session)) -> SentMessageResponse:
    message = session.exec(select(SentMessage).where(SentMessage.sent_message_id == sent_message_id)).first()
    if message is None:
        raise _not_found("Sent message")
    return _sent_message_response(message, session)


@router.post("/send-batches", response_model=SendBatchResponse)
def send_batch(request: SendBatchRequest, session: Session = Depends(get_session)) -> SendBatchResponse:
    result = SendBatchService(session=session).approve_and_send(request.intent_ids, request.reviewer_id)
    session.commit()
    return _send_batch_response(result)


@router.post("/outreach-records/{outreach_record_id}/resolve", response_model=OutreachResolutionResponse)
def resolve_outreach_record(
    outreach_record_id: str,
    request: OutreachResolutionRequest,
    session: Session = Depends(get_session),
) -> OutreachResolutionResponse:
    try:
        result = OutreachResolutionService(session).resolve(
            outreach_record_id,
            resolution=request.resolution,
            reviewer_id=request.reviewer_id,
            comment=request.comment,
        )
        session.commit()
    except OutreachResolutionError as exc:
        status_code = 404 if exc.code == "outreach_record_missing" else 400
        raise HTTPException(status_code=status_code, detail={"code": exc.code, "message": str(exc)}) from exc
    return OutreachResolutionResponse(
        outreach_record=_outreach_record_response(result.record),
        previous_status=result.previous_status,
        resolution=result.resolution,
    )


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
