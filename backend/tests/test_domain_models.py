from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import Session, SQLModel, create_engine, select

from backend.app.db.models import (
    Company,
    Contact,
    EmailDraft,
    FitEvaluation,
    ImportedFile,
    ImportedGateResult,
    MasterCvProfileSnapshot,
    OutreachRecord,
    PolicySnapshot,
    SendIntent,
    SendReservation,
    UserProfileSnapshot,
)


def test_phase2_domain_records_can_be_persisted_with_links(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'domain-models.db'}")
    SQLModel.metadata.create_all(engine)

    now = datetime.now(timezone.utc)
    with Session(engine) as session:
        imported_file = ImportedFile(
            run_id="run-1",
            path="runs/run-1/output/send_intent.json",
            filename="send_intent.json",
            schema_name="send_intent",
            sha256="hash",
            size_bytes=123,
            status="valid",
            raw_json="{}",
        )
        session.add(imported_file)
        session.flush()

        user_profile = UserProfileSnapshot(
            profile_id="profile-1",
            schema_version="1.0",
            content_hash="profile-hash",
            raw_json="{}",
            imported_file_id=imported_file.id,
        )
        master_cv = MasterCvProfileSnapshot(
            profile_id="master-cv-1",
            schema_version="1.0",
            content_hash="cv-hash",
            raw_json="{}",
            imported_file_id=imported_file.id,
        )
        policy = PolicySnapshot(
            policy_id="policy-1",
            schema_version="1.0",
            content_hash="policy-hash",
            raw_json="{}",
            imported_file_id=imported_file.id,
        )
        company = Company(
            company_id="company-1",
            name="Example GmbH",
            normalized_domain="example.com",
            normalized_name="example gmbh",
            company_policy_key="example.com",
            company_policy_key_kind="domain",
            confidence=0.95,
            raw_json="{}",
            imported_file_id=imported_file.id,
        )
        session.add_all([user_profile, master_cv, policy, company])
        session.flush()

        contact = Contact(
            contact_id="contact-1",
            company_id=company.id,
            external_company_id=company.company_id,
            name="Hiring Lead",
            role_title="Engineering Manager",
            raw_email="Hiring.Lead@example.com",
            normalized_recipient_email="hiring.lead@example.com",
            email_source="public_professional_listing",
            confidence=0.9,
            raw_json="{}",
            imported_file_id=imported_file.id,
        )
        fit_evaluation = FitEvaluation(
            evaluation_id="fit-1",
            company_id=company.id,
            external_company_id=company.company_id,
            user_profile_snapshot_id=user_profile.id,
            policy_snapshot_id=policy.id,
            fit_score=0.82,
            decision="pursue",
            confidence=0.88,
            raw_json="{}",
            imported_file_id=imported_file.id,
        )
        session.add_all([contact, fit_evaluation])
        session.flush()

        draft = EmailDraft(
            draft_id="draft-1",
            company_id=company.id,
            external_company_id=company.company_id,
            contact_id=contact.id,
            external_contact_id=contact.contact_id,
            subject="Initiative application",
            body_text="Hello",
            claim_refs_json='["claim-1"]',
            confidence=0.86,
            raw_json="{}",
            imported_file_id=imported_file.id,
        )
        session.add(draft)
        session.flush()

        intent = SendIntent(
            intent_id="intent-1",
            run_id="run-1",
            company_id=company.id,
            external_company_id=company.company_id,
            contact_id=contact.id,
            external_contact_id=contact.contact_id,
            email_draft_id=draft.id,
            external_email_draft_id=draft.draft_id,
            raw_recipient_email=contact.raw_email,
            normalized_recipient_email=contact.normalized_recipient_email,
            recipient_name=contact.name,
            company_domain=company.normalized_domain,
            subject=draft.subject,
            body_text=draft.body_text,
            claim_refs_json=draft.claim_refs_json,
            policy_snapshot_id=policy.id,
            external_policy_id=policy.policy_id,
            user_profile_snapshot_id=user_profile.id,
            external_profile_id=user_profile.profile_id,
            master_cv_profile_snapshot_id=master_cv.id,
            external_master_cv_profile_id=master_cv.profile_id,
            confidence=0.84,
            created_by="codex_file_worker",
            raw_json="{}",
            imported_file_id=imported_file.id,
        )
        session.add(intent)
        session.flush()

        gate_result = ImportedGateResult(
            gate_result_id="gate-1",
            send_intent_id=intent.id,
            external_intent_id=intent.intent_id,
            status="blocked",
            reasons_json='["evaluate_only_imported"]',
            evaluated_at=now,
            policy_snapshot_id=policy.id,
            external_policy_id=policy.policy_id,
            raw_json="{}",
            imported_file_id=imported_file.id,
        )
        reservation = SendReservation(
            reservation_id="reservation-1",
            send_intent_id=intent.id,
            normalized_recipient_email=intent.normalized_recipient_email,
            company_id=company.id,
            company_policy_key=company.company_policy_key,
            policy_snapshot_id=policy.id,
            status="active",
        )
        outreach_record = OutreachRecord(
            outreach_record_id="outreach-1",
            send_intent_id=intent.id,
            company_id=company.id,
            contact_id=contact.id,
            normalized_recipient_email=intent.normalized_recipient_email,
            company_policy_key=company.company_policy_key,
            policy_snapshot_id=policy.id,
            status="sent",
        )
        session.add_all([gate_result, reservation, outreach_record])
        session.commit()

    with Session(engine) as session:
        stored_intent = session.exec(select(SendIntent).where(SendIntent.intent_id == "intent-1")).one()
        stored_reservation = session.exec(select(SendReservation)).one()
        stored_outreach = session.exec(select(OutreachRecord)).one()

    assert stored_intent.external_policy_id == "policy-1"
    assert stored_intent.external_profile_id == "profile-1"
    assert stored_intent.external_master_cv_profile_id == "master-cv-1"
    assert stored_reservation.status == "active"
    assert stored_outreach.company_policy_key == "example.com"
