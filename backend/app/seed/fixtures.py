from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

from sqlmodel import Session

from backend.app.db.models import (
    Company,
    Contact,
    EmailDraft,
    MasterCvProfileSnapshot,
    PolicySnapshot,
    SendIntent,
    UserProfileSnapshot,
)
from backend.app.db.normalization import (
    build_company_policy_key,
    normalize_company_domain,
    normalize_company_name,
    normalize_recipient_email,
)


SEED_RUN_ID = "seed-run-phase2"
SEED_CREATED_AT = datetime(2026, 1, 15, 9, 0, tzinfo=timezone.utc)


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _content_hash(value: Any) -> str:
    return sha256(_stable_json(value).encode("utf-8")).hexdigest()


_SEED_PAYLOADS: dict[str, list[dict[str, Any]]] = {
    "user_profiles": [
        {
            "schema_version": "1.0",
            "profile_id": "seed-user-profile-1",
            "created_at": "2026-01-15T09:00:00Z",
            "identity": {
                "display_name": "Avery Example",
                "headline": "Backend systems candidate",
                "location": "Berlin, Germany",
                "email": "avery.example@example.com",
                "links": ["https://portfolio.example.com/avery"],
            },
            "preferences": {
                "target_roles": [
                    {
                        "value": "Backend Engineer",
                        "provenance": {
                            "source_type": "user_claim",
                            "confidence": 1.0,
                            "needs_review": False,
                            "source_refs": ["seed-preference-roles"],
                        },
                    }
                ],
                "target_locations": [
                    {
                        "value": "Remote Europe",
                        "provenance": {
                            "source_type": "user_claim",
                            "confidence": 1.0,
                            "needs_review": False,
                            "source_refs": ["seed-preference-location"],
                        },
                    }
                ],
                "remote_preferences": ["remote", "hybrid"],
                "communication_tone": {
                    "value": "concise and professional",
                    "provenance": {
                        "source_type": "user_claim",
                        "confidence": 1.0,
                        "needs_review": False,
                        "source_refs": ["seed-preference-tone"],
                    },
                },
            },
            "provenance_summary": {
                "source_documents": ["seed-user-profile.md"],
                "interview_notes": [],
            },
        }
    ],
    "master_cv_profiles": [
        {
            "schema_version": "1.0",
            "profile_id": "seed-master-cv-1",
            "created_at": "2026-01-15T09:00:00Z",
            "claims": [
                {
                    "claim_id": "seed-claim-backend-systems",
                    "category": "skill",
                    "statement": "Built deterministic backend workflows for structured data validation.",
                    "tags": ["backend", "validation"],
                    "approved_for_tailoring": True,
                    "provenance": {
                        "source_type": "verified_document",
                        "confidence": 1.0,
                        "needs_review": False,
                        "source_refs": ["seed-master-cv.md"],
                    },
                }
            ],
            "preferred_cv_sections": ["experience", "projects", "skills"],
        }
    ],
    "policies": [
        {
            "schema_version": "1.0",
            "policy_id": "seed-policy-1",
            "created_at": "2026-01-15T09:00:00Z",
            "exclusions": {
                "industries": [],
                "company_names": [],
                "domains": [],
                "keywords": [],
            },
            "outreach": {
                "allow_company_repeat": False,
                "allow_recipient_repeat": False,
                "company_dedupe_window_days": 365,
                "recipient_dedupe_window_days": 365,
                "require_manual_review_before_send": True,
            },
            "limits": {
                "daily_send_limit": 3,
                "weekly_send_limit": 10,
            },
            "review_thresholds": {
                "minimum_required_confidence": 0.8,
                "block_needs_review_required_fields": True,
            },
            "forbidden_claims": [],
        }
    ],
    "companies": [
        {
            "schema_version": "1.0",
            "company_id": "seed-company-northstar",
            "name": "Northstar Demo Robotics",
            "domain": "https://www.northstar-demo.example.com/careers",
            "description": "Fictional robotics company used for local development fixtures.",
            "industry_tags": ["robotics", "developer-tools"],
            "locations": ["Berlin", "Remote Europe"],
            "remote_policy": "hybrid",
            "source_refs": ["seed-company-source-northstar"],
            "confidence": 0.96,
            "review_flags": [],
        },
        {
            "schema_version": "1.0",
            "company_id": "seed-company-greenloop",
            "name": "Greenloop Demo Systems",
            "domain": "greenloop-demo.example.org",
            "description": "Fictional climate software company used for local development fixtures.",
            "industry_tags": ["climate", "software"],
            "locations": ["Remote"],
            "remote_policy": "remote",
            "source_refs": ["seed-company-source-greenloop"],
            "confidence": 0.94,
            "review_flags": [],
        },
    ],
    "contacts": [
        {
            "schema_version": "1.0",
            "contact_id": "seed-contact-northstar",
            "company_id": "seed-company-northstar",
            "name": "Riley Hiring",
            "role_title": "Engineering Hiring Lead",
            "email": "Riley.Hiring@northstar-demo.example.com",
            "email_source": "company_site",
            "profile_url": "https://northstar-demo.example.com/team/riley",
            "confidence": 0.93,
            "source_refs": ["seed-contact-source-northstar"],
            "review_flags": [],
        },
        {
            "schema_version": "1.0",
            "contact_id": "seed-contact-greenloop",
            "company_id": "seed-company-greenloop",
            "name": "Jordan Talent",
            "role_title": "Talent Partner",
            "email": "Jordan.Talent@greenloop-demo.example.org",
            "email_source": "company_site",
            "profile_url": "https://greenloop-demo.example.org/team/jordan",
            "confidence": 0.91,
            "source_refs": ["seed-contact-source-greenloop"],
            "review_flags": [],
        },
    ],
    "email_drafts": [
        {
            "schema_version": "1.0",
            "draft_id": "seed-draft-northstar",
            "company_id": "seed-company-northstar",
            "contact_id": "seed-contact-northstar",
            "subject": "Backend systems interest",
            "body_text": "Hello Riley, this is deterministic local seed content for review only. It must not be sent.",
            "tone": "concise",
            "claim_refs": ["seed-claim-backend-systems"],
            "source_refs": ["seed-draft-source-northstar"],
            "attachments": [],
            "confidence": 0.89,
            "review_flags": ["seed_fixture_review_only"],
        },
        {
            "schema_version": "1.0",
            "draft_id": "seed-draft-greenloop",
            "company_id": "seed-company-greenloop",
            "contact_id": "seed-contact-greenloop",
            "subject": "Deterministic workflow interest",
            "body_text": "Hello Jordan, this is deterministic local seed content for review only. It must not be sent.",
            "tone": "concise",
            "claim_refs": ["seed-claim-backend-systems"],
            "source_refs": ["seed-draft-source-greenloop"],
            "attachments": [],
            "confidence": 0.88,
            "review_flags": ["seed_fixture_review_only"],
        },
    ],
    "send_intents": [
        {
            "schema_version": "1.0",
            "intent_id": "seed-intent-northstar",
            "run_id": SEED_RUN_ID,
            "company_id": "seed-company-northstar",
            "contact_id": "seed-contact-northstar",
            "email_draft_id": "seed-draft-northstar",
            "recipient_email": "Riley.Hiring@northstar-demo.example.com",
            "recipient_name": "Riley Hiring",
            "company_domain": "northstar-demo.example.com",
            "subject": "Backend systems interest",
            "body_text": "Hello Riley, this is deterministic local seed content for review only. It must not be sent.",
            "attachments": [],
            "source_refs": ["seed-intent-source-northstar"],
            "claim_refs": ["seed-claim-backend-systems"],
            "policy_id": "seed-policy-1",
            "profile_id": "seed-user-profile-1",
            "master_cv_profile_id": "seed-master-cv-1",
            "confidence": 0.87,
            "review_flags": ["seed_fixture_review_only"],
            "created_by": "codex_agent",
        },
        {
            "schema_version": "1.0",
            "intent_id": "seed-intent-greenloop",
            "run_id": SEED_RUN_ID,
            "company_id": "seed-company-greenloop",
            "contact_id": "seed-contact-greenloop",
            "email_draft_id": "seed-draft-greenloop",
            "recipient_email": "Jordan.Talent@greenloop-demo.example.org",
            "recipient_name": "Jordan Talent",
            "company_domain": "greenloop-demo.example.org",
            "subject": "Deterministic workflow interest",
            "body_text": "Hello Jordan, this is deterministic local seed content for review only. It must not be sent.",
            "attachments": [],
            "source_refs": ["seed-intent-source-greenloop"],
            "claim_refs": ["seed-claim-backend-systems"],
            "policy_id": "seed-policy-1",
            "profile_id": "seed-user-profile-1",
            "master_cv_profile_id": "seed-master-cv-1",
            "confidence": 0.86,
            "review_flags": ["seed_fixture_review_only"],
            "created_by": "codex_agent",
        },
    ],
}


@dataclass(frozen=True)
class Phase2SeedRecords:
    user_profile: UserProfileSnapshot
    master_cv_profile: MasterCvProfileSnapshot
    policy: PolicySnapshot
    companies: list[Company]
    contacts: list[Contact]
    email_drafts: list[EmailDraft]
    send_intents: list[SendIntent]


def phase2_seed_payloads() -> dict[str, list[dict[str, Any]]]:
    return copy.deepcopy(_SEED_PAYLOADS)


def add_phase2_seed_records(session: Session) -> Phase2SeedRecords:
    payloads = phase2_seed_payloads()

    user_profile_payload = payloads["user_profiles"][0]
    master_cv_payload = payloads["master_cv_profiles"][0]
    policy_payload = payloads["policies"][0]

    user_profile = UserProfileSnapshot(
        profile_id=user_profile_payload["profile_id"],
        schema_version=user_profile_payload["schema_version"],
        source_created_at=SEED_CREATED_AT,
        content_hash=_content_hash(user_profile_payload),
        raw_json=_stable_json(user_profile_payload),
        imported_at=SEED_CREATED_AT,
    )
    master_cv_profile = MasterCvProfileSnapshot(
        profile_id=master_cv_payload["profile_id"],
        schema_version=master_cv_payload["schema_version"],
        source_created_at=SEED_CREATED_AT,
        content_hash=_content_hash(master_cv_payload),
        raw_json=_stable_json(master_cv_payload),
        imported_at=SEED_CREATED_AT,
    )
    policy = PolicySnapshot(
        policy_id=policy_payload["policy_id"],
        schema_version=policy_payload["schema_version"],
        source_created_at=SEED_CREATED_AT,
        content_hash=_content_hash(policy_payload),
        raw_json=_stable_json(policy_payload),
        imported_at=SEED_CREATED_AT,
    )
    session.add_all([user_profile, master_cv_profile, policy])
    session.flush()

    companies: list[Company] = []
    for payload in payloads["companies"]:
        normalized_domain = normalize_company_domain(payload["domain"])
        normalized_name = normalize_company_name(payload["name"])
        company_policy_key, company_policy_key_kind = build_company_policy_key(
            normalized_domain=normalized_domain,
            normalized_name=normalized_name,
        )
        companies.append(
            Company(
                company_id=payload["company_id"],
                name=payload["name"],
                raw_domain=payload["domain"],
                normalized_domain=normalized_domain,
                normalized_name=normalized_name,
                company_policy_key=company_policy_key,
                company_policy_key_kind=company_policy_key_kind,
                description=payload["description"],
                industry_tags_json=_stable_json(payload["industry_tags"]),
                locations_json=_stable_json(payload["locations"]),
                remote_policy=payload["remote_policy"],
                source_refs_json=_stable_json(payload["source_refs"]),
                confidence=payload["confidence"],
                review_flags_json=_stable_json(payload["review_flags"]),
                raw_json=_stable_json(payload),
                created_at=SEED_CREATED_AT,
                updated_at=SEED_CREATED_AT,
            )
        )
    session.add_all(companies)
    session.flush()
    companies_by_external_id = {company.company_id: company for company in companies}

    contacts: list[Contact] = []
    for payload in payloads["contacts"]:
        company = companies_by_external_id[payload["company_id"]]
        contacts.append(
            Contact(
                contact_id=payload["contact_id"],
                company_id=company.id,
                external_company_id=company.company_id,
                name=payload["name"],
                role_title=payload["role_title"],
                raw_email=payload["email"],
                normalized_recipient_email=normalize_recipient_email(payload["email"]),
                email_source=payload["email_source"],
                profile_url=payload["profile_url"],
                source_refs_json=_stable_json(payload["source_refs"]),
                confidence=payload["confidence"],
                review_flags_json=_stable_json(payload["review_flags"]),
                raw_json=_stable_json(payload),
                created_at=SEED_CREATED_AT,
                updated_at=SEED_CREATED_AT,
            )
        )
    session.add_all(contacts)
    session.flush()
    contacts_by_external_id = {contact.contact_id: contact for contact in contacts}

    email_drafts: list[EmailDraft] = []
    for payload in payloads["email_drafts"]:
        company = companies_by_external_id[payload["company_id"]]
        contact = contacts_by_external_id[payload["contact_id"]]
        email_drafts.append(
            EmailDraft(
                draft_id=payload["draft_id"],
                company_id=company.id,
                external_company_id=company.company_id,
                contact_id=contact.id,
                external_contact_id=contact.contact_id,
                subject=payload["subject"],
                body_text=payload["body_text"],
                tone=payload["tone"],
                claim_refs_json=_stable_json(payload["claim_refs"]),
                source_refs_json=_stable_json(payload["source_refs"]),
                attachments_json=_stable_json(payload["attachments"]),
                confidence=payload["confidence"],
                review_flags_json=_stable_json(payload["review_flags"]),
                raw_json=_stable_json(payload),
                created_at=SEED_CREATED_AT,
            )
        )
    session.add_all(email_drafts)
    session.flush()
    drafts_by_external_id = {draft.draft_id: draft for draft in email_drafts}

    send_intents: list[SendIntent] = []
    for payload in payloads["send_intents"]:
        company = companies_by_external_id[payload["company_id"]]
        contact = contacts_by_external_id[payload["contact_id"]]
        draft = drafts_by_external_id[payload["email_draft_id"]]
        send_intents.append(
            SendIntent(
                intent_id=payload["intent_id"],
                run_id=payload["run_id"],
                company_id=company.id,
                external_company_id=company.company_id,
                contact_id=contact.id,
                external_contact_id=contact.contact_id,
                email_draft_id=draft.id,
                external_email_draft_id=draft.draft_id,
                raw_recipient_email=payload["recipient_email"],
                normalized_recipient_email=normalize_recipient_email(payload["recipient_email"]),
                recipient_name=payload["recipient_name"],
                company_domain=payload["company_domain"],
                subject=payload["subject"],
                body_text=payload["body_text"],
                attachments_json=_stable_json(payload["attachments"]),
                source_refs_json=_stable_json(payload["source_refs"]),
                claim_refs_json=_stable_json(payload["claim_refs"]),
                policy_snapshot_id=policy.id,
                external_policy_id=policy.policy_id,
                user_profile_snapshot_id=user_profile.id,
                external_profile_id=user_profile.profile_id,
                master_cv_profile_snapshot_id=master_cv_profile.id,
                external_master_cv_profile_id=master_cv_profile.profile_id,
                confidence=payload["confidence"],
                review_flags_json=_stable_json(payload["review_flags"]),
                created_by=payload["created_by"],
                status="imported",
                raw_json=_stable_json(payload),
                created_at=SEED_CREATED_AT,
                updated_at=SEED_CREATED_AT,
            )
        )
    session.add_all(send_intents)
    session.flush()

    return Phase2SeedRecords(
        user_profile=user_profile,
        master_cv_profile=master_cv_profile,
        policy=policy,
        companies=companies,
        contacts=contacts,
        email_drafts=email_drafts,
        send_intents=send_intents,
    )
