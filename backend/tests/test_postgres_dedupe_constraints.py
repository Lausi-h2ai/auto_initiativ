from __future__ import annotations

import os
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, create_engine

from backend.app.core.config import get_settings
from backend.app.db.models import SendReservation


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


@pytest.fixture()
def postgres_engine(monkeypatch):
    database_url = os.environ.get("POSTGRES_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("POSTGRES_TEST_DATABASE_URL is not configured.")

    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()
    command.upgrade(Config(os.path.join(PROJECT_ROOT, "alembic.ini")), "head")
    return create_engine(database_url)


def test_postgres_partial_unique_dedupe_constraints(postgres_engine):
    suffix = uuid4().hex
    email = f"lead-{suffix}@example.com"
    company_key = f"domain:example-{suffix}.com"

    with Session(postgres_engine) as session:
        session.add(
            SendReservation(
                reservation_id=f"reservation-{suffix}-1",
                normalized_recipient_email=email,
                company_policy_key=company_key,
                status="active",
            )
        )
        session.commit()

    with pytest.raises(IntegrityError):
        with Session(postgres_engine) as session:
            session.add(
                SendReservation(
                    reservation_id=f"reservation-{suffix}-2",
                    normalized_recipient_email=email,
                    company_policy_key=f"domain:other-{suffix}.com",
                    status="reserved",
                )
            )
            session.commit()
