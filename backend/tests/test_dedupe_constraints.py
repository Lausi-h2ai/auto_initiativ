from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, SQLModel, create_engine

from backend.app.db.models import OutreachRecord, SendReservation


@pytest.fixture()
def session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'dedupe.db'}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as db_session:
        yield db_session


def _commit(session: Session, *records) -> None:
    session.add_all(records)
    session.commit()


def test_duplicate_active_reservation_recipient_is_rejected(session: Session):
    _commit(
        session,
        SendReservation(
            reservation_id="reservation-1",
            normalized_recipient_email="lead@example.com",
            company_policy_key="domain:example.com",
            status="active",
        ),
    )

    with pytest.raises(IntegrityError):
        _commit(
            session,
            SendReservation(
                reservation_id="reservation-2",
                normalized_recipient_email="lead@example.com",
                company_policy_key="domain:other.example",
                status="reserved",
            ),
        )


def test_inactive_reservation_recipient_does_not_block_new_active_reservation(session: Session):
    _commit(
        session,
        SendReservation(
            reservation_id="reservation-1",
            normalized_recipient_email="lead@example.com",
            company_policy_key="domain:example.com",
            status="released",
        ),
        SendReservation(
            reservation_id="reservation-2",
            normalized_recipient_email="lead@example.com",
            company_policy_key="domain:other.example",
            status="active",
        ),
    )


def test_duplicate_active_reservation_company_is_rejected(session: Session):
    _commit(
        session,
        SendReservation(
            reservation_id="reservation-1",
            normalized_recipient_email="one@example.com",
            company_policy_key="domain:example.com",
            status="active",
        ),
    )

    with pytest.raises(IntegrityError):
        _commit(
            session,
            SendReservation(
                reservation_id="reservation-2",
                normalized_recipient_email="two@example.com",
                company_policy_key="domain:example.com",
                status="active",
            ),
        )


def test_company_dedupe_flag_allows_policy_permitted_parallel_reservations(session: Session):
    _commit(
        session,
        SendReservation(
            reservation_id="reservation-1",
            normalized_recipient_email="one@example.com",
            company_policy_key="domain:example.com",
            status="active",
            dedupe_company=False,
        ),
        SendReservation(
            reservation_id="reservation-2",
            normalized_recipient_email="two@example.com",
            company_policy_key="domain:example.com",
            status="active",
            dedupe_company=False,
        ),
    )


def test_duplicate_contacted_recipient_is_rejected(session: Session):
    _commit(
        session,
        OutreachRecord(
            outreach_record_id="outreach-1",
            normalized_recipient_email="lead@example.com",
            company_policy_key="domain:example.com",
            status="sent",
        ),
    )

    with pytest.raises(IntegrityError):
        _commit(
            session,
            OutreachRecord(
                outreach_record_id="outreach-2",
                normalized_recipient_email="lead@example.com",
                company_policy_key="domain:other.example",
                status="contacted",
            ),
        )


def test_duplicate_contacted_company_is_rejected(session: Session):
    _commit(
        session,
        OutreachRecord(
            outreach_record_id="outreach-1",
            normalized_recipient_email="one@example.com",
            company_policy_key="domain:example.com",
            status="sent",
        ),
    )

    with pytest.raises(IntegrityError):
        _commit(
            session,
            OutreachRecord(
                outreach_record_id="outreach-2",
                normalized_recipient_email="two@example.com",
                company_policy_key="domain:example.com",
                status="delivered",
            ),
        )


def test_non_contacted_outreach_status_does_not_block_completed_outreach(session: Session):
    _commit(
        session,
        OutreachRecord(
            outreach_record_id="outreach-1",
            normalized_recipient_email="lead@example.com",
            company_policy_key="domain:example.com",
            status="drafted",
        ),
        OutreachRecord(
            outreach_record_id="outreach-2",
            normalized_recipient_email="lead@example.com",
            company_policy_key="domain:example.com",
            status="sent",
        ),
    )
