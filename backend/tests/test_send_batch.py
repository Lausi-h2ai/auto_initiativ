from __future__ import annotations

import json
from datetime import timedelta

from sqlmodel import select

from backend.app.db.models import AuditLog, OutreachRecord, SendApprovalSnapshot, SendIntent, SendReservation, SentMessage, utc_now
from backend.app.core.config import Settings
from backend.app.email_delivery.adapters import EmailDeliveryResult, FakeDryRunEmailAdapter
from backend.app.email_delivery.batch_send import KnownUnsentEmailError, SendBatchService
from backend.app.gates.evaluate_only import EvaluateOnlyGateService
from backend.app.imports.import_service import RunImportService
from backend.app.onboarding.promotion import OnboardingPromotionService, SnapshotPromotionRequest
from backend.tests.conftest import copy_valid_run


def _promotion_request() -> SnapshotPromotionRequest:
    return SnapshotPromotionRequest(
        reviewer_id="test-reviewer",
        confirm_user_profile=True,
        confirm_master_cv_profile=True,
        confirm_policy=True,
    )


def _import_approved_run(db_session, runs_root, run_id: str = "send-batch-valid") -> None:
    output = copy_valid_run(runs_root, run_id)
    attachments = output / "attachments"
    attachments.mkdir(exist_ok=True)
    (attachments / "cv.pdf").write_bytes(b"%PDF-1.4\nfake cv\n")
    result = RunImportService(db_session).import_run(run_id)
    assert result.run.status == "imported"
    promotion = OnboardingPromotionService(db_session).promote_run_snapshots(run_id, _promotion_request())
    assert promotion.status == "approved"
    db_session.commit()


class _AcceptedAdapter(FakeDryRunEmailAdapter):
    provider = "test_provider"

    def send(self, message):
        self.messages.append(message)
        return EmailDeliveryResult(
            provider=self.provider,
            status="provider_accepted",
            intent_id=message.intent_id,
            recipient_email=message.recipient_email,
            provider_message_id="provider-message-1",
            provider_thread_id="thread-1",
            network_performed=False,
            metadata={"accepted": True},
        )


class _AcceptedGmailAdapter(_AcceptedAdapter):
    provider = "gmail"


class _KnownUnsentAdapter(FakeDryRunEmailAdapter):
    provider = "known_unsent"

    def send(self, message):
        raise KnownUnsentEmailError("provider rejected before accepting")


class _UncertainAdapter(FakeDryRunEmailAdapter):
    provider = "uncertain"

    def send(self, message):
        raise RuntimeError("connection dropped after dispatch")


def test_send_batch_freezes_payload_and_records_sent_ledger(db_session, runs_root):
    _import_approved_run(db_session, runs_root)
    adapter = _AcceptedAdapter()

    result = SendBatchService(db_session, adapter=adapter, sending_enabled=True).approve_and_send(["intent-1"], "local-user")
    db_session.commit()

    assert result.status == "completed"
    assert result.items[0].status == "sent"
    assert len(adapter.messages) == 1
    assert adapter.messages[0].subject == "Application for backend role"
    assert adapter.messages[0].headers["X-Auto-Initiativ-Intent-ID"] == "intent-1"

    approval = db_session.exec(select(SendApprovalSnapshot)).one()
    assert approval.external_intent_id == "intent-1"
    assert approval.payload_hash
    attachments = json.loads(approval.attachments_json)
    assert attachments[0]["sha256"]

    sent_message = db_session.exec(select(SentMessage)).one()
    assert sent_message.status == "provider_accepted"
    assert sent_message.provider_message_id == "provider-message-1"

    outreach = db_session.exec(select(OutreachRecord)).one()
    assert outreach.status == "sent"
    assert outreach.company_policy_key == "domain:example.com"

    intent = db_session.exec(select(SendIntent).where(SendIntent.intent_id == "intent-1")).one()
    assert intent.status == "sent"

    reservation = db_session.exec(select(SendReservation)).one()
    assert reservation.status == "released"


def test_sent_messages_endpoint_exposes_frozen_payload_and_provider_link(client, db_session, runs_root):
    _import_approved_run(db_session, runs_root)
    adapter = _AcceptedGmailAdapter()

    result = SendBatchService(db_session, adapter=adapter, sending_enabled=True).approve_and_send(["intent-1"], "local-user")
    db_session.commit()

    response = client.get("/sent-messages")

    assert result.items[0].status == "sent"
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    sent = body[0]
    assert sent["external_intent_id"] == "intent-1"
    assert sent["normalized_recipient_email"] == "alex.hiring@example.com"
    assert sent["subject"] == "Application for backend role"
    assert sent["body_text"].startswith("Hello")
    assert sent["provider"] == "gmail"
    assert sent["provider_message_id"] == "provider-message-1"
    assert sent["provider_url"] == "https://mail.google.com/mail/u/0/#all/thread-1"

    detail = client.get(f"/sent-messages/{sent['sent_message_id']}")
    assert detail.status_code == 200
    assert detail.json()["attachments"][0]["attachment_id"] == "attachment-1"


def test_known_unsent_provider_failure_does_not_create_blocking_outreach(db_session, runs_root):
    _import_approved_run(db_session, runs_root)

    result = SendBatchService(db_session, adapter=_KnownUnsentAdapter(), sending_enabled=True).approve_and_send(["intent-1"], "local-user")
    db_session.commit()

    assert result.items[0].status == "send_failed_known_unsent"
    assert db_session.exec(select(OutreachRecord)).all() == []
    sent_message = db_session.exec(select(SentMessage)).one()
    assert sent_message.status == "provider_rejected_known_unsent"
    reservation = db_session.exec(select(SendReservation)).one()
    assert reservation.status == "failed_known_unsent"


def test_uncertain_provider_failure_creates_blocking_outreach_until_resolved(db_session, runs_root):
    _import_approved_run(db_session, runs_root)

    result = SendBatchService(db_session, adapter=_UncertainAdapter(), sending_enabled=True).approve_and_send(["intent-1"], "local-user")
    db_session.commit()

    assert result.items[0].status == "send_failed_uncertain"
    outreach = db_session.exec(select(OutreachRecord)).one()
    assert outreach.status == "outcome_uncertain"
    intent = db_session.exec(select(SendIntent).where(SendIntent.intent_id == "intent-1")).one()
    assert intent.status == "send_failed_uncertain"
    reservation = db_session.exec(select(SendReservation)).one()
    assert reservation.status == "outcome_uncertain"

    blocked = EvaluateOnlyGateService(db_session).evaluate("intent-1")
    assert blocked.gate_result.status == "blocked"
    assert any(reason["code"] == "duplicate_recipient" for reason in blocked.reasons)


def test_dedupe_window_allows_old_contacted_records(db_session, runs_root):
    _import_approved_run(db_session, runs_root)
    intent = db_session.exec(select(SendIntent).where(SendIntent.intent_id == "intent-1")).one()
    db_session.add(
        OutreachRecord(
            outreach_record_id="outreach-old",
            send_intent_id=intent.id,
            normalized_recipient_email=intent.normalized_recipient_email,
            company_policy_key="domain:example.com",
            status="sent",
            occurred_at=utc_now() - timedelta(days=366),
        )
    )
    db_session.commit()

    result = EvaluateOnlyGateService(db_session).evaluate("intent-1")

    assert result.gate_result.status == "passed_evaluate_only"


def test_send_batch_api_is_disabled_by_default_but_freezes_approval(client, runs_root):
    output = copy_valid_run(runs_root, "api-send-disabled")
    attachments = output / "attachments"
    attachments.mkdir(exist_ok=True)
    (attachments / "cv.pdf").write_bytes(b"%PDF-1.4\nfake cv\n")
    import_response = client.post("/runs/api-send-disabled/import")
    assert import_response.status_code == 200
    promotion_response = client.post(
        "/onboarding/runs/api-send-disabled/promote",
        json={
            "reviewer_id": "test-reviewer",
            "confirm_user_profile": True,
            "confirm_master_cv_profile": True,
            "confirm_policy": True,
        },
    )
    assert promotion_response.status_code == 200
    response = client.post("/send-batches", json={"intent_ids": ["intent-1"], "reviewer_id": "local-user"})

    assert response.status_code == 200
    body = response.json()
    assert body["items"][0]["status"] == "send_disabled"
    audit_response = client.get("/audit-logs", params={"action": "send_approval_snapshot_created"})
    assert audit_response.status_code == 200


def test_email_delivery_settings_endpoint_reports_safe_default(client):
    response = client.get("/email-delivery/settings")

    assert response.status_code == 200
    body = response.json()
    assert body["sending_enabled"] is False
    assert body["provider"] == "gmail_sandbox"
    assert body["allow_real_recipients"] is False
    assert body["mode"] == "disabled"


def test_gmail_sandbox_mode_rewrites_recipient_before_provider_send(db_session, runs_root, monkeypatch):
    _import_approved_run(db_session, runs_root)
    adapter = _AcceptedAdapter()

    monkeypatch.setattr("backend.app.email_delivery.batch_send.GmailEmailAdapter", lambda settings: adapter)
    settings = Settings(
        email_sending_enabled=True,
        email_provider="gmail_sandbox",
        gmail_sandbox_recipient="laurent.hug@gmx.de",
    )

    result = SendBatchService(db_session, settings=settings).approve_and_send(["intent-1"], "local-user")
    db_session.commit()

    assert result.items[0].status == "sent"
    assert len(adapter.messages) == 1
    message = adapter.messages[0]
    assert message.recipient_email == "laurent.hug@gmx.de"
    assert message.subject.startswith("[SANDBOX to alex.hiring@example.com]")
    assert "Original recipient: alex.hiring@example.com" in message.body_text
    assert message.headers["X-Auto-Initiativ-Original-Recipient"] == "alex.hiring@example.com"


def test_real_gmail_mode_requires_explicit_real_recipient_opt_in(db_session, runs_root, monkeypatch):
    _import_approved_run(db_session, runs_root)
    adapter = _AcceptedAdapter()

    monkeypatch.setattr("backend.app.email_delivery.batch_send.GmailEmailAdapter", lambda settings: adapter)
    settings = Settings(email_sending_enabled=True, email_provider="gmail", email_allow_real_recipients=False)

    result = SendBatchService(db_session, settings=settings).approve_and_send(["intent-1"], "local-user")
    db_session.commit()

    assert result.items[0].status == "send_failed_known_unsent"
    assert result.items[0].reason_codes == ["provider_rejected_known_unsent"]
    assert adapter.messages == []
    assert db_session.exec(select(OutreachRecord)).all() == []
