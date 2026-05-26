from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlmodel import Session, select

from backend.app.db.models import AuditLog, OutreachRecord


ALLOWED_OUTREACH_RESOLUTIONS = {"mark_sent", "mark_not_sent", "keep_blocked", "void_record"}


class OutreachResolutionError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class OutreachResolutionResult:
    record: OutreachRecord
    previous_status: str
    resolution: str


def _json_dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _json_loads(value: str | None, fallback: Any) -> Any:
    if value is None:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


class OutreachResolutionService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def resolve(
        self,
        outreach_record_id: str,
        *,
        resolution: str,
        reviewer_id: str,
        comment: str,
    ) -> OutreachResolutionResult:
        if resolution not in ALLOWED_OUTREACH_RESOLUTIONS:
            raise OutreachResolutionError("invalid_resolution", "Unsupported outreach resolution.")
        if not comment.strip():
            raise OutreachResolutionError("resolution_comment_required", "A resolution comment is required.")

        record = self.session.exec(select(OutreachRecord).where(OutreachRecord.outreach_record_id == outreach_record_id)).first()
        if record is None:
            raise OutreachResolutionError("outreach_record_missing", "Outreach record could not be resolved.")

        previous_status = record.status
        next_status = {
            "mark_sent": "sent",
            "mark_not_sent": "provider_rejected_known_unsent",
            "keep_blocked": "outcome_uncertain",
            "void_record": "void",
        }[resolution]
        record.status = next_status
        notes = _json_loads(record.notes_json, {})
        notes.setdefault("resolution_history", []).append(
            {
                "resolution": resolution,
                "reviewer_id": reviewer_id,
                "comment": comment,
                "previous_status": previous_status,
                "new_status": next_status,
            }
        )
        record.notes_json = _json_dumps(notes)
        self.session.add(record)
        self.session.add(
            AuditLog(
                run_id=None,
                actor_type="user",
                action="outreach_record_resolved",
                entity_type="outreach_record",
                entity_id=record.outreach_record_id,
                result_status=next_status,
                reason_codes_json=_json_dumps([resolution]),
                metadata_json=_json_dumps(
                    {
                        "reviewer_id": reviewer_id,
                        "comment": comment,
                        "previous_status": previous_status,
                        "new_status": next_status,
                    }
                ),
            )
        )
        self.session.flush()
        return OutreachResolutionResult(record=record, previous_status=previous_status, resolution=resolution)
