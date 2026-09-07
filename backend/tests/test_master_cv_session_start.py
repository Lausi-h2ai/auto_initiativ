"""Exercise session startup without launching an external agent process."""

import json
from datetime import datetime, timezone

from backend.app.core.config import get_settings
from backend.app.db.models import MasterCvProfileSnapshot
from backend.app.master_cv.routes import start_session


def test_master_cv_session_starts_without_spurious_agent_unavailable(db_session):
    profile = {
        "schema_version": "1.0",
        "profile_id": "profile-session-start",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "claims": [],
    }
    db_session.add(MasterCvProfileSnapshot(
        profile_id=profile["profile_id"], schema_version="1.0",
        content_hash="session-start-profile", status="approved",
        raw_json=json.dumps(profile), source_created_at=datetime.now(timezone.utc),
    ))
    db_session.commit()

    class OfflineAdapter:
        def prepare_agent_workspace(self, run_id, instructions):
            pass

        def start_or_attach(self, run_id):
            pass

        def ensure_recruiter_prompt(self, run_id, prompt, *, require_plain_reply):
            pass

        def transcript_entries(self, run_id):
            return []

    result = start_session(session=db_session, settings=get_settings(), adapter=OfflineAdapter())

    assert result["status"] == "active", result.get("error")
    assert result["candidate"]["profile_id"] == profile["profile_id"]
