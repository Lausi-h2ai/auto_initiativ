from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any

from sqlmodel import Session, col, select

from backend.app.db.models import (
    AuditLog,
    ImportedFile,
    MasterCvProfileSnapshot,
    PolicySnapshot,
    UserProfileSnapshot,
)

SNAPSHOT_STATUS_CANDIDATE = "candidate"
SNAPSHOT_STATUS_APPROVED = "approved"
SNAPSHOT_STATUS_REJECTED = "rejected"
SNAPSHOT_STATUS_SUPERSEDED = "superseded"
PROMOTABLE_STATUSES = {SNAPSHOT_STATUS_CANDIDATE, SNAPSHOT_STATUS_APPROVED}
APPROVED_PROVENANCE_TYPES = {"verified_document", "user_claim"}


@dataclass(frozen=True)
class SnapshotPromotionRequest:
    reviewer_id: str
    confirm_user_profile: bool
    confirm_master_cv_profile: bool
    confirm_policy: bool


@dataclass(frozen=True)
class SnapshotPromotionIssue:
    code: str
    message: str
    snapshot_type: str | None = None
    field: str | None = None

    def as_dict(self) -> dict[str, str]:
        payload = {"code": self.code, "message": self.message}
        if self.snapshot_type is not None:
            payload["snapshot_type"] = self.snapshot_type
        if self.field is not None:
            payload["field"] = self.field
        return payload


@dataclass(frozen=True)
class PromotedSnapshot:
    snapshot_type: str
    id: int
    external_id: str
    status: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "snapshot_type": self.snapshot_type,
            "id": self.id,
            "external_id": self.external_id,
            "status": self.status,
        }


@dataclass(frozen=True)
class SnapshotPromotionResult:
    run_id: str
    status: str
    promoted: list[PromotedSnapshot] = field(default_factory=list)
    issues: list[SnapshotPromotionIssue] = field(default_factory=list)


class OnboardingPromotionService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def promote_run_snapshots(self, run_id: str, request: SnapshotPromotionRequest) -> SnapshotPromotionResult:
        snapshots = self._snapshots_for_run(run_id)
        issues = self._validate_request(request)
        issues.extend(self._validate_snapshots(snapshots, request))

        if issues:
            result = SnapshotPromotionResult(run_id=run_id, status="blocked", issues=issues)
            self._audit(run_id, request, result)
            self.session.flush()
            return result

        user_profile = snapshots["user_profile"]
        if request.confirm_user_profile and isinstance(user_profile, UserProfileSnapshot):
            self._record_user_profile_confirmation(user_profile)

        promoted: list[PromotedSnapshot] = []
        for snapshot_type, snapshot in snapshots.items():
            self._supersede_other_approved(snapshot_type, snapshot)
            snapshot.status = SNAPSHOT_STATUS_APPROVED
            self.session.add(snapshot)
            promoted.append(
                PromotedSnapshot(
                    snapshot_type=snapshot_type,
                    id=snapshot.id or 0,
                    external_id=self._external_id(snapshot),
                    status=snapshot.status,
                )
            )

        result = SnapshotPromotionResult(run_id=run_id, status="approved", promoted=promoted)
        self._audit(run_id, request, result)
        self.session.flush()
        return result

    def _snapshots_for_run(self, run_id: str) -> dict[str, UserProfileSnapshot | MasterCvProfileSnapshot | PolicySnapshot | None]:
        imported_file_ids = [
            file_id
            for file_id in self.session.exec(select(ImportedFile.id).where(ImportedFile.run_id == run_id)).all()
            if file_id is not None
        ]
        if not imported_file_ids:
            return {"user_profile": None, "master_cv_profile": None, "policy": None}

        return {
            "user_profile": self.session.exec(
                select(UserProfileSnapshot).where(col(UserProfileSnapshot.imported_file_id).in_(imported_file_ids))
            ).first(),
            "master_cv_profile": self.session.exec(
                select(MasterCvProfileSnapshot).where(col(MasterCvProfileSnapshot.imported_file_id).in_(imported_file_ids))
            ).first(),
            "policy": self.session.exec(select(PolicySnapshot).where(col(PolicySnapshot.imported_file_id).in_(imported_file_ids))).first(),
        }

    def _validate_request(self, request: SnapshotPromotionRequest) -> list[SnapshotPromotionIssue]:
        issues: list[SnapshotPromotionIssue] = []
        if not request.reviewer_id.strip():
            issues.append(SnapshotPromotionIssue("reviewer_missing", "Promotion requires a reviewer ID."))
        confirmations = {
            "user_profile": request.confirm_user_profile,
            "master_cv_profile": request.confirm_master_cv_profile,
            "policy": request.confirm_policy,
        }
        for snapshot_type, confirmed in confirmations.items():
            if not confirmed:
                issues.append(
                    SnapshotPromotionIssue(
                        "review_confirmation_missing",
                        "Promotion requires explicit reviewer confirmation.",
                        snapshot_type=snapshot_type,
                    )
                )
        return issues

    def _validate_snapshots(
        self,
        snapshots: dict[str, UserProfileSnapshot | MasterCvProfileSnapshot | PolicySnapshot | None],
        request: SnapshotPromotionRequest,
    ) -> list[SnapshotPromotionIssue]:
        issues: list[SnapshotPromotionIssue] = []
        for snapshot_type, snapshot in snapshots.items():
            if snapshot is None:
                issues.append(
                    SnapshotPromotionIssue(
                        "snapshot_missing",
                        "Required onboarding snapshot is missing for this run.",
                        snapshot_type=snapshot_type,
                    )
                )
                continue
            if snapshot.status not in PROMOTABLE_STATUSES:
                issues.append(
                    SnapshotPromotionIssue(
                        "snapshot_status_not_promotable",
                        "Snapshot status is not promotable.",
                        snapshot_type=snapshot_type,
                        field="status",
                    )
                )

        user_profile = snapshots["user_profile"]
        if isinstance(user_profile, UserProfileSnapshot):
            issues.extend(self._validate_user_profile(user_profile, confirmed=request.confirm_user_profile))

        master_cv = snapshots["master_cv_profile"]
        if isinstance(master_cv, MasterCvProfileSnapshot):
            issues.extend(self._validate_master_cv(master_cv))

        policy = snapshots["policy"]
        if isinstance(policy, PolicySnapshot):
            issues.extend(self._validate_policy(policy))

        return issues

    def _validate_user_profile(self, snapshot: UserProfileSnapshot, *, confirmed: bool) -> list[SnapshotPromotionIssue]:
        data = _json_object(snapshot.raw_json)
        return [
            SnapshotPromotionIssue(
                "review_needed_provenance",
                "User profile contains provenance that still requires review.",
                snapshot_type="user_profile",
                field=path,
            )
            for path, provenance in _iter_provenance(data)
            if _provenance_requires_review(provenance)
            and not (confirmed and provenance.get("source_type") == "user_claim")
        ]

    def _record_user_profile_confirmation(self, snapshot: UserProfileSnapshot) -> None:
        data = _json_object(snapshot.raw_json)
        changed = False
        for _path, provenance in _iter_provenance(data):
            if not _provenance_requires_review(provenance) or provenance.get("source_type") != "user_claim":
                continue
            source_refs = provenance.get("source_refs") if isinstance(provenance.get("source_refs"), list) else []
            provenance.update(
                {
                    "confidence": 1.0,
                    "needs_review": False,
                    "source_refs": list(dict.fromkeys([*source_refs, "profile_review:user_confirmation"])),
                }
            )
            changed = True
        review_items = data.get("review_items")
        approved_fields = {
            field_key
            for path, provenance in _iter_provenance(data)
            if not _provenance_requires_review(provenance) and (field_key := _profile_field_key(path))
        }
        if isinstance(review_items, list) and approved_fields:
            retained_items = [
                item
                for item in review_items
                if not isinstance(item, dict) or _profile_field_key(str(item.get("field") or "")) not in approved_fields
            ]
            if len(retained_items) != len(review_items):
                data["review_items"] = retained_items
                changed = True
        if not changed:
            return
        raw_json = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        snapshot.raw_json = raw_json
        snapshot.content_hash = sha256(raw_json.encode("utf-8")).hexdigest()
        self.session.add(snapshot)

    def _validate_master_cv(self, snapshot: MasterCvProfileSnapshot) -> list[SnapshotPromotionIssue]:
        data = _json_object(snapshot.raw_json)
        issues: list[SnapshotPromotionIssue] = []
        seen_claim_ids: set[str] = set()
        for index, claim in enumerate(data.get("claims", [])):
            if not isinstance(claim, dict):
                continue
            claim_id = claim.get("claim_id")
            field = f"claims[{index}]"
            if isinstance(claim_id, str):
                if claim_id in seen_claim_ids:
                    issues.append(
                        SnapshotPromotionIssue(
                            "duplicate_claim_id",
                            "Master CV claim IDs must be unique within a promoted snapshot.",
                            snapshot_type="master_cv_profile",
                            field=f"{field}.claim_id",
                        )
                    )
                seen_claim_ids.add(claim_id)
            if claim.get("approved_for_tailoring") is True and _provenance_requires_review(claim.get("provenance")):
                issues.append(
                    SnapshotPromotionIssue(
                        "approved_claim_requires_review",
                        "Approved tailoring claims must have approved provenance.",
                        snapshot_type="master_cv_profile",
                        field=f"{field}.provenance",
                    )
                )
        return issues

    def _validate_policy(self, snapshot: PolicySnapshot) -> list[SnapshotPromotionIssue]:
        data = _json_object(snapshot.raw_json)
        issues: list[SnapshotPromotionIssue] = []
        exclusions = data.get("exclusions", {})
        if isinstance(exclusions, dict):
            for bucket in ("industries", "company_names", "domains", "keywords"):
                for index, item in enumerate(exclusions.get(bucket, [])):
                    provenance = item.get("provenance") if isinstance(item, dict) else None
                    if _provenance_requires_review(provenance):
                        issues.append(
                            SnapshotPromotionIssue(
                                "policy_exclusion_requires_review",
                                "Policy exclusions require approved provenance before promotion.",
                                snapshot_type="policy",
                                field=f"exclusions.{bucket}[{index}].provenance",
                            )
                        )

        limits = data.get("limits", {})
        if not isinstance(limits, dict) or limits.get("daily_send_limit") is None or limits.get("weekly_send_limit") is None:
            issues.append(
                SnapshotPromotionIssue(
                    "send_limits_missing",
                    "Policy promotion requires explicit daily and weekly send limits.",
                    snapshot_type="policy",
                    field="limits",
                )
            )

        review_thresholds = data.get("review_thresholds", {})
        if not isinstance(review_thresholds, dict) or review_thresholds.get("block_needs_review_required_fields") is not True:
            issues.append(
                SnapshotPromotionIssue(
                    "review_defaults_not_conservative",
                    "Policy promotion requires needs-review required fields to remain blocked.",
                    snapshot_type="policy",
                    field="review_thresholds.block_needs_review_required_fields",
                )
            )
        return issues

    def _supersede_other_approved(
        self,
        snapshot_type: str,
        snapshot: UserProfileSnapshot | MasterCvProfileSnapshot | PolicySnapshot,
    ) -> None:
        model = {
            "user_profile": UserProfileSnapshot,
            "master_cv_profile": MasterCvProfileSnapshot,
            "policy": PolicySnapshot,
        }[snapshot_type]
        for existing in self.session.exec(select(model).where(model.status == SNAPSHOT_STATUS_APPROVED)).all():
            if existing.id != snapshot.id:
                existing.status = SNAPSHOT_STATUS_SUPERSEDED
                self.session.add(existing)

    def _audit(self, run_id: str, request: SnapshotPromotionRequest, result: SnapshotPromotionResult) -> None:
        self.session.add(
            AuditLog(
                run_id=run_id,
                actor_type="backend",
                action="onboarding_promotion_completed",
                entity_type="onboarding_promotion",
                entity_id=run_id,
                result_status=result.status,
                reason_codes_json=_json_dumps([issue.code for issue in result.issues]),
                metadata_json=_json_dumps(
                    {
                        "reviewer_id": request.reviewer_id,
                        "promoted": [snapshot.as_dict() for snapshot in result.promoted],
                        "issues": [issue.as_dict() for issue in result.issues],
                    }
                ),
            )
        )

    def _external_id(self, snapshot: UserProfileSnapshot | MasterCvProfileSnapshot | PolicySnapshot) -> str:
        if isinstance(snapshot, PolicySnapshot):
            return snapshot.policy_id
        return snapshot.profile_id


def _json_dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _json_object(raw_json: str) -> dict[str, Any]:
    data = json.loads(raw_json)
    return data if isinstance(data, dict) else {}


def _iter_provenance(value: Any, path: str = "$") -> list[tuple[str, dict[str, Any]]]:
    found: list[tuple[str, dict[str, Any]]] = []
    if isinstance(value, dict):
        provenance = value.get("provenance")
        if isinstance(provenance, dict):
            found.append((f"{path}.provenance", provenance))
        for key, child in value.items():
            found.extend(_iter_provenance(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(_iter_provenance(child, f"{path}[{index}]"))
    return found


def _provenance_requires_review(provenance: Any) -> bool:
    if not isinstance(provenance, dict):
        return True
    return provenance.get("needs_review") is True or provenance.get("source_type") not in APPROVED_PROVENANCE_TYPES


def _profile_field_key(path: str) -> tuple[str, ...]:
    normalized_path = path.strip().removeprefix("$.").removeprefix("/").removesuffix(".provenance")
    parts = re.split(r"[./\[\]]+", normalized_path)
    return tuple(
        normalized
        for part in parts
        if (normalized := re.sub(r"[^a-z0-9]+", "_", part.strip().lower()).strip("_"))
    )
