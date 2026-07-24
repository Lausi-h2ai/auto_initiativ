from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sqlmodel import Session, select

from backend.app.db.models import (
    AuditLog,
    MasterCvProfileSnapshot,
    ReviewException,
    UserProfileSnapshot,
    utc_now,
)


PROFILE_REFRESH_CATEGORY = "profile_refresh_suggested"


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def suggest_profile_refresh_if_old(
    session: Session,
    *,
    user_profile: UserProfileSnapshot | None,
    master_cv_profile: MasterCvProfileSnapshot | None,
    threshold_days: int,
    campaign_id: int | None = None,
) -> ReviewException | None:
    """Create one non-blocking reminder for an unchanged approved profile pair."""
    if user_profile is None or master_cv_profile is None:
        return None
    if user_profile.workspace_id != master_cv_profile.workspace_id:
        raise ValueError("Profile freshness snapshots must belong to the same workspace.")

    exception_id = f"profile-refresh-{user_profile.id}-{master_cv_profile.id}"
    existing_query = select(ReviewException).where(
        ReviewException.exception_id == exception_id
    )
    if user_profile.workspace_id is not None:
        existing_query = existing_query.where(
            ReviewException.workspace_id == user_profile.workspace_id
        )
    existing = session.exec(existing_query).first()
    if existing is not None:
        return existing

    last_profile_change = max(
        _aware(user_profile.imported_at),
        _aware(master_cv_profile.imported_at),
    )
    if utc_now() - last_profile_change <= timedelta(days=threshold_days):
        return None

    reminder = ReviewException(
        workspace_id=user_profile.workspace_id,
        exception_id=exception_id,
        campaign_id=campaign_id,
        category=PROFILE_REFRESH_CATEGORY,
        title="Your career profile may be worth a quick refresh",
        explanation=(
            f"Your approved profile has not changed in more than {threshold_days} days. "
            "CV generation will continue with the currently approved facts; nothing is blocked or changed automatically."
        ),
        recommended_action=(
            "Open the onboarding recruiter if you want to review recent experience, projects, skills, or preferences. "
            "Only changes you explicitly approve will be used in future CVs."
        ),
    )
    session.add(reminder)
    session.add(
        AuditLog(
            workspace_id=user_profile.workspace_id,
            actor_type="system",
            action="profile_refresh_suggested",
            entity_type="user_profile_snapshot",
            entity_id=user_profile.profile_id,
            result_status="created",
            metadata_json=json.dumps(
                {
                    "threshold_days": threshold_days,
                    "user_profile_snapshot_id": user_profile.id,
                    "master_cv_profile_snapshot_id": master_cv_profile.id,
                    "last_profile_change": last_profile_change.isoformat(),
                }
            ),
        )
    )
    session.commit()
    session.refresh(reminder)
    return reminder
