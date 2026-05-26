from __future__ import annotations

import json

import pytest
from sqlmodel import select

from backend.app.db.models import AuditLog, OutreachRecord
from backend.app.email_delivery.resolution import OutreachResolutionError, OutreachResolutionService


def _outreach() -> OutreachRecord:
    return OutreachRecord(
        outreach_record_id="outreach-1",
        normalized_recipient_email="lead@example.com",
        company_policy_key="domain:example.com",
        status="outcome_uncertain",
        notes_json="{}",
    )


def test_outreach_resolution_marks_known_unsent_and_audits(db_session):
    db_session.add(_outreach())
    db_session.commit()

    result = OutreachResolutionService(db_session).resolve(
        "outreach-1",
        resolution="mark_not_sent",
        reviewer_id="local-user",
        comment="Gmail search confirmed no message was sent.",
    )
    db_session.commit()

    assert result.previous_status == "outcome_uncertain"
    assert result.record.status == "provider_rejected_known_unsent"
    notes = json.loads(result.record.notes_json)
    assert notes["resolution_history"][0]["comment"] == "Gmail search confirmed no message was sent."
    audit = db_session.exec(select(AuditLog).where(AuditLog.action == "outreach_record_resolved")).one()
    assert audit.actor_type == "user"


def test_outreach_resolution_requires_comment(db_session):
    db_session.add(_outreach())
    db_session.commit()

    with pytest.raises(OutreachResolutionError) as exc_info:
        OutreachResolutionService(db_session).resolve(
            "outreach-1",
            resolution="mark_sent",
            reviewer_id="local-user",
            comment="",
        )

    assert exc_info.value.code == "resolution_comment_required"
