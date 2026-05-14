from __future__ import annotations

import json

from sqlmodel import Session, SQLModel, create_engine, select

from backend.app.db.models import (
    Company,
    Contact,
    EmailDraft,
    ImportedGateResult,
    MasterCvProfileSnapshot,
    OutreachRecord,
    PolicySnapshot,
    SendIntent,
    SendReservation,
    UserProfileSnapshot,
)
from backend.app.seed.fixtures import SEED_CREATED_AT, add_phase2_seed_records, phase2_seed_payloads


def test_phase2_seed_payloads_are_fake_safe_and_deterministic():
    first_payloads = phase2_seed_payloads()
    second_payloads = phase2_seed_payloads()

    assert first_payloads == second_payloads
    first_payloads["user_profiles"][0]["profile_id"] = "mutated"
    assert phase2_seed_payloads()["user_profiles"][0]["profile_id"] == "seed-user-profile-1"

    serialized = json.dumps(second_payloads, sort_keys=True).lower()
    for forbidden in ["gmail", "smtp", "password", "secret", "api_key", "openai"]:
        assert forbidden not in serialized

    recipient_emails = [payload["email"] for payload in second_payloads["contacts"]]
    assert recipient_emails == [
        "Riley.Hiring@northstar-demo.example.com",
        "Jordan.Talent@greenloop-demo.example.org",
    ]
    assert all("example." in email for email in recipient_emails)


def test_phase2_seed_records_persist_domain_fixture_graph(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'seed-fixtures.db'}")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        records = add_phase2_seed_records(session)
        session.commit()

        assert records.user_profile.id is not None
        assert records.master_cv_profile.id is not None
        assert records.policy.id is not None
        assert len(records.companies) == 2
        assert len(records.contacts) == 2
        assert len(records.email_drafts) == 2
        assert len(records.send_intents) == 2

    with Session(engine) as session:
        assert len(session.exec(select(UserProfileSnapshot)).all()) == 1
        assert len(session.exec(select(MasterCvProfileSnapshot)).all()) == 1
        assert len(session.exec(select(PolicySnapshot)).all()) == 1
        assert len(session.exec(select(Company)).all()) == 2
        assert len(session.exec(select(Contact)).all()) == 2
        assert len(session.exec(select(EmailDraft)).all()) == 2
        assert len(session.exec(select(SendIntent)).all()) == 2

        northstar = session.exec(select(Company).where(Company.company_id == "seed-company-northstar")).one()
        northstar_contact = session.exec(
            select(Contact).where(Contact.contact_id == "seed-contact-northstar")
        ).one()
        northstar_intent = session.exec(
            select(SendIntent).where(SendIntent.intent_id == "seed-intent-northstar")
        ).one()

        assert northstar.normalized_domain == "northstar-demo.example.com"
        assert northstar.company_policy_key == "domain:northstar-demo.example.com"
        assert northstar.company_policy_key_kind == "domain"
        assert northstar_contact.company_id == northstar.id
        assert northstar_contact.normalized_recipient_email == "riley.hiring@northstar-demo.example.com"
        assert northstar_intent.company_id == northstar.id
        assert northstar_intent.contact_id == northstar_contact.id
        assert northstar_intent.policy_snapshot_id is not None
        assert northstar_intent.status == "imported"
        assert northstar_intent.created_at == SEED_CREATED_AT.replace(tzinfo=None)


def test_phase2_seed_records_do_not_create_gate_reservations_or_outreach(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'seed-boundaries.db'}")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        add_phase2_seed_records(session)
        session.commit()

    with Session(engine) as session:
        assert session.exec(select(ImportedGateResult)).all() == []
        assert session.exec(select(SendReservation)).all() == []
        assert session.exec(select(OutreachRecord)).all() == []
