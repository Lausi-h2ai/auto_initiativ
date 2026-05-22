from __future__ import annotations

import json

from sqlmodel import select

from backend.app.db.models import AuditLog, MasterCvProfileSnapshot, PolicySnapshot, UserProfileSnapshot
from backend.app.imports.import_service import RunImportService
from backend.app.onboarding.promotion import OnboardingPromotionService, SnapshotPromotionRequest
from backend.tests.conftest import copy_valid_run


def _request() -> SnapshotPromotionRequest:
    return SnapshotPromotionRequest(
        reviewer_id="test-reviewer",
        confirm_user_profile=True,
        confirm_master_cv_profile=True,
        confirm_policy=True,
    )


def _import_valid_run(db_session, runs_root, run_id: str = "onboarding-promote") -> None:
    copy_valid_run(runs_root, run_id)
    result = RunImportService(db_session).import_run(run_id)
    assert result.run.status == "imported"


def _rewrite_raw(snapshot, mutator) -> None:
    data = json.loads(snapshot.raw_json)
    mutator(data)
    snapshot.raw_json = json.dumps(data)


def test_imported_onboarding_snapshots_start_as_candidates(db_session, runs_root):
    _import_valid_run(db_session, runs_root)

    user_profile = db_session.exec(select(UserProfileSnapshot)).one()
    master_cv = db_session.exec(select(MasterCvProfileSnapshot)).one()
    policy = db_session.exec(select(PolicySnapshot)).one()

    assert user_profile.status == "candidate"
    assert master_cv.status == "candidate"
    assert policy.status == "candidate"


def test_promote_run_snapshots_approves_candidates_and_audits(db_session, runs_root):
    _import_valid_run(db_session, runs_root)

    result = OnboardingPromotionService(db_session).promote_run_snapshots("onboarding-promote", _request())
    db_session.commit()

    assert result.status == "approved"
    assert result.issues == []
    assert {snapshot.snapshot_type for snapshot in result.promoted} == {"user_profile", "master_cv_profile", "policy"}
    assert db_session.exec(select(UserProfileSnapshot)).one().status == "approved"
    assert db_session.exec(select(MasterCvProfileSnapshot)).one().status == "approved"
    assert db_session.exec(select(PolicySnapshot)).one().status == "approved"

    audit = db_session.exec(select(AuditLog).where(AuditLog.action == "onboarding_promotion_completed")).one()
    assert audit.result_status == "approved"
    assert json.loads(audit.reason_codes_json) == []
    assert json.loads(audit.metadata_json)["reviewer_id"] == "test-reviewer"


def test_promotion_supersedes_prior_approved_snapshots(db_session, runs_root):
    _import_valid_run(db_session, runs_root)
    old_user_profile = UserProfileSnapshot(
        profile_id="old-profile",
        schema_version="1.0",
        content_hash="old-user",
        status="approved",
        raw_json="{}",
    )
    old_master_cv = MasterCvProfileSnapshot(
        profile_id="old-master-cv",
        schema_version="1.0",
        content_hash="old-master",
        status="approved",
        raw_json="{}",
    )
    old_policy = PolicySnapshot(
        policy_id="old-policy",
        schema_version="1.0",
        content_hash="old-policy",
        status="approved",
        raw_json="{}",
    )
    db_session.add_all([old_user_profile, old_master_cv, old_policy])
    db_session.commit()

    result = OnboardingPromotionService(db_session).promote_run_snapshots("onboarding-promote", _request())
    db_session.commit()

    assert result.status == "approved"
    assert db_session.get(UserProfileSnapshot, old_user_profile.id).status == "superseded"
    assert db_session.get(MasterCvProfileSnapshot, old_master_cv.id).status == "superseded"
    assert db_session.get(PolicySnapshot, old_policy.id).status == "superseded"


def test_promotion_requires_explicit_reviewer_confirmations(db_session, runs_root):
    _import_valid_run(db_session, runs_root)

    result = OnboardingPromotionService(db_session).promote_run_snapshots(
        "onboarding-promote",
        SnapshotPromotionRequest(
            reviewer_id="test-reviewer",
            confirm_user_profile=True,
            confirm_master_cv_profile=True,
            confirm_policy=False,
        ),
    )
    db_session.commit()

    assert result.status == "blocked"
    assert "review_confirmation_missing" in {issue.code for issue in result.issues}
    assert db_session.exec(select(PolicySnapshot)).one().status == "candidate"


def test_promotion_blocks_approved_claims_with_review_needed_provenance(db_session, runs_root):
    _import_valid_run(db_session, runs_root)
    master_cv = db_session.exec(select(MasterCvProfileSnapshot)).one()
    _rewrite_raw(
        master_cv,
        lambda data: data["claims"][0]["provenance"].update({"source_type": "needs_review", "needs_review": True}),
    )
    db_session.add(master_cv)
    db_session.commit()

    result = OnboardingPromotionService(db_session).promote_run_snapshots("onboarding-promote", _request())

    assert result.status == "blocked"
    assert "approved_claim_requires_review" in {issue.code for issue in result.issues}


def test_promotion_blocks_duplicate_master_cv_claim_ids(db_session, runs_root):
    _import_valid_run(db_session, runs_root)
    master_cv = db_session.exec(select(MasterCvProfileSnapshot)).one()
    _rewrite_raw(master_cv, lambda data: data["claims"].append(dict(data["claims"][0])))
    db_session.add(master_cv)
    db_session.commit()

    result = OnboardingPromotionService(db_session).promote_run_snapshots("onboarding-promote", _request())

    assert result.status == "blocked"
    assert "duplicate_claim_id" in {issue.code for issue in result.issues}


def test_promotion_blocks_non_conservative_policy_defaults(db_session, runs_root):
    _import_valid_run(db_session, runs_root)
    policy = db_session.exec(select(PolicySnapshot)).one()
    _rewrite_raw(policy, lambda data: data["outreach"].update({"require_manual_review_before_send": False}))
    db_session.add(policy)
    db_session.commit()

    result = OnboardingPromotionService(db_session).promote_run_snapshots("onboarding-promote", _request())

    assert result.status == "blocked"
    assert "manual_review_policy_not_conservative" in {issue.code for issue in result.issues}


def test_onboarding_promotion_api_promotes_without_send_endpoint(client, runs_root):
    copy_valid_run(runs_root, "onboarding-api")
    assert client.post("/runs/onboarding-api/import").status_code == 200

    snapshots = client.get("/onboarding/runs/onboarding-api/snapshots")
    assert snapshots.status_code == 200
    assert {snapshot["status"] for snapshot in snapshots.json()} == {"candidate"}

    response = client.post(
        "/onboarding/runs/onboarding-api/promote",
        json={
            "reviewer_id": "test-reviewer",
            "confirm_user_profile": True,
            "confirm_master_cv_profile": True,
            "confirm_policy": True,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "approved"
    assert {snapshot["status"] for snapshot in body["promoted"]} == {"approved"}
    assert client.post("/send").status_code == 404
