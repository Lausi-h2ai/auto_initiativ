from __future__ import annotations

from datetime import timedelta

import pytest
from sqlmodel import select

from backend.app.db.models import (
    AuditLog,
    MasterCvProfileSnapshot,
    ReviewException,
    UserProfileSnapshot,
    utc_now,
)
from backend.app.profiles.freshness import suggest_profile_refresh_if_old


def _profiles(
    db_session,
    *,
    workspace_id: int = 1,
    user_age_days: int = 121,
    master_age_days: int = 121,
    suffix: str = "one",
) -> tuple[UserProfileSnapshot, MasterCvProfileSnapshot]:
    user_profile = UserProfileSnapshot(
        workspace_id=workspace_id,
        profile_id=f"user-{suffix}",
        schema_version="1.0",
        content_hash=f"user-hash-{suffix}",
        status="approved",
        raw_json="{}",
        imported_at=utc_now() - timedelta(days=user_age_days),
    )
    master_profile = MasterCvProfileSnapshot(
        workspace_id=workspace_id,
        profile_id=f"master-{suffix}",
        schema_version="1.0",
        content_hash=f"master-hash-{suffix}",
        status="approved",
        raw_json="{}",
        imported_at=utc_now() - timedelta(days=master_age_days),
    )
    db_session.add_all([user_profile, master_profile])
    db_session.commit()
    db_session.refresh(user_profile)
    db_session.refresh(master_profile)
    return user_profile, master_profile


def test_old_profile_pair_creates_one_non_blocking_audited_reminder(db_session):
    user_profile, master_profile = _profiles(db_session)

    first = suggest_profile_refresh_if_old(
        db_session,
        user_profile=user_profile,
        master_cv_profile=master_profile,
        threshold_days=120,
        campaign_id=42,
    )
    second = suggest_profile_refresh_if_old(
        db_session,
        user_profile=user_profile,
        master_cv_profile=master_profile,
        threshold_days=120,
        campaign_id=99,
    )

    assert first is not None
    assert second is not None
    assert second.id == first.id
    assert first.workspace_id == 1
    assert first.campaign_id == 42
    assert first.status == "open"
    assert "nothing is blocked" in first.explanation
    reminders = db_session.exec(
        select(ReviewException).where(
            ReviewException.category == "profile_refresh_suggested"
        )
    ).all()
    audits = db_session.exec(
        select(AuditLog).where(AuditLog.action == "profile_refresh_suggested")
    ).all()
    assert len(reminders) == 1
    assert len(audits) == 1
    assert audits[0].workspace_id == 1


@pytest.mark.parametrize(
    ("user_age_days", "master_age_days"),
    [(30, 121), (121, 30), (119, 119)],
)
def test_reminder_requires_both_snapshots_to_exceed_threshold(
    db_session,
    user_age_days,
    master_age_days,
):
    user_profile, master_profile = _profiles(
        db_session,
        user_age_days=user_age_days,
        master_age_days=master_age_days,
    )

    assert (
        suggest_profile_refresh_if_old(
            db_session,
            user_profile=user_profile,
            master_cv_profile=master_profile,
            threshold_days=120,
        )
        is None
    )


def test_dismissed_pair_stays_dismissed_and_new_pair_can_create_reminder(db_session):
    user_profile, master_profile = _profiles(db_session)
    reminder = suggest_profile_refresh_if_old(
        db_session,
        user_profile=user_profile,
        master_cv_profile=master_profile,
        threshold_days=120,
    )
    assert reminder is not None
    reminder.status = "resolved"
    reminder.resolution = "skip"
    db_session.add(reminder)
    db_session.commit()

    same_pair = suggest_profile_refresh_if_old(
        db_session,
        user_profile=user_profile,
        master_cv_profile=master_profile,
        threshold_days=120,
    )
    next_user, next_master = _profiles(db_session, suffix="two")
    next_pair = suggest_profile_refresh_if_old(
        db_session,
        user_profile=next_user,
        master_cv_profile=next_master,
        threshold_days=120,
    )

    assert same_pair is not None
    assert same_pair.status == "resolved"
    assert next_pair is not None
    assert next_pair.id != same_pair.id


def test_profile_pair_must_be_workspace_consistent(db_session):
    user_profile, _ = _profiles(db_session, workspace_id=1, suffix="one")
    _, master_profile = _profiles(db_session, workspace_id=2, suffix="two")

    with pytest.raises(ValueError, match="same workspace"):
        suggest_profile_refresh_if_old(
            db_session,
            user_profile=user_profile,
            master_cv_profile=master_profile,
            threshold_days=120,
        )
