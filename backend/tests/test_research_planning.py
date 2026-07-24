from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from backend.app.db.models import (
    AgentTask,
    AuditLog,
    Campaign,
    CampaignCompany,
    CampaignJob,
    Company,
    JobPosting,
    ResearchDiscovery,
    ResearchPlan,
    ResearchTarget,
)
from backend.app.research.planning import compile_research_plan, confirm_plan, plan_hash, replace_pending_plan
from backend.app.workflow.engine import WorkflowEngine


SCHEMA = Path("schemas/research_plan.schema.json")


def test_compile_plan_normalizes_bare_remote_and_preserves_order_and_guidance():
    campaign = Campaign(
        campaign_id="campaign-balanced",
        name="Balanced",
        campaign_type="listed_job_search",
        brief_json=json.dumps(
            {
                "role_focus": "Praktikum Softwareentwicklung",
                "locations": ["Switzerland", "Konstanz", "Remote", " remote "],
                "additional_guidance": "Mindestens 6 Wochen, nicht zu weit entfernt außer 100% remote.",
            }
        ),
    )

    plan = compile_research_plan(campaign, schema_path=SCHEMA)

    assert [target["label"] for target in plan["targets"]] == ["Switzerland", "Konstanz", "Remote Europe"]
    assert [target["kind"] for target in plan["targets"]] == ["geographic", "geographic", "remote"]
    assert all(target["required_attempts"] == 3 for target in plan["targets"])
    assert plan["additional_guidance"].startswith("Mindestens 6 Wochen")
    constraints = {item["key"]: item["value"] for item in plan["hard_constraints"]}
    assert constraints["employment_type"] == "internship"
    assert constraints["minimum_duration_weeks"] == 6
    assert constraints["work_mode"] == "fully_remote"
    assert constraints["remote_region"] == "Europe"
    assert plan["review_flags"] == ["vague_distance_preference"]


@pytest.mark.parametrize(
    ("campaign_type", "candidate_kind"),
    [
        ("initiative_outreach", "company"),
        ("listed_job_search", "job"),
    ],
)
def test_balanced_budget_is_campaign_wide_for_company_and_job_search(campaign_type, candidate_kind):
    campaign = Campaign(
        campaign_id=f"campaign-{candidate_kind}-budget",
        name="Balanced global budget",
        campaign_type=campaign_type,
        brief_json=json.dumps(
            {
                "role_focus": "Applied AI",
                "locations": ["Zurich", "Basel", "Remote"],
                "search_breadth": "balanced",
                "time_budget_minutes": 999,
                "max_companies": 99,
                "max_jobs": 99,
            }
        ),
    )

    plan = compile_research_plan(campaign, schema_path=SCHEMA)

    assert plan["schema_version"] == "1.1"
    assert plan["effort"] == {
        "mode": "balanced",
        "candidate_kind": candidate_kind,
        "candidate_goal": 30,
        "time_budget_seconds": 1800,
        "max_parallel_targets": 3,
        "allocation_policy": "equal_floor_shared_pool",
        "shared_candidate_pool": 6,
        "shared_time_pool_seconds": 360,
    }
    assert [target["guaranteed_candidate_goal"] for target in plan["targets"]] == [8, 8, 8]
    assert [target["guaranteed_time_seconds"] for target in plan["targets"]] == [480, 480, 480]


def test_company_preferences_is_a_backward_compatible_guidance_alias():
    campaign = Campaign(
        campaign_id="campaign-legacy-field",
        name="Legacy field",
        campaign_type="initiative_outreach",
        brief_json=json.dumps(
            {
                "role_focus": "Applied AI",
                "locations": ["Berlin"],
                "company_preferences": "Prefer useful climate products.",
            }
        ),
    )

    plan = compile_research_plan(campaign, schema_path=SCHEMA)

    assert plan["additional_guidance"] == "Prefer useful climate products."
    assert plan["soft_preferences"] == [
        {"text": "Prefer useful climate products.", "source": "campaign_guidance"}
    ]


def test_plan_confirmation_pins_the_compiled_hash(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'planning.db'}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        campaign = Campaign(
            campaign_id="campaign-confirm",
            name="Confirm",
            campaign_type="listed_job_search",
            brief_json=json.dumps({"role_focus": "AI internship", "locations": ["Remote"]}),
        )
        session.add(campaign)
        session.commit()
        session.refresh(campaign)

        payload = compile_research_plan(campaign, schema_path=SCHEMA)
        record = replace_pending_plan(session, campaign, payload)
        targets = session.exec(select(ResearchTarget).where(ResearchTarget.research_plan_id == record.id)).all()

        assert record.status == "pending_confirmation"
        assert record.content_hash == plan_hash(payload)
        assert len(targets) == 1
        assert targets[0].label == "Remote Europe"

        confirm_plan(record)
        session.add(record)
        session.commit()
        session.refresh(record)

        assert record.status == "confirmed"
        assert record.confirmed_hash == record.content_hash


def test_balanced_company_research_finalization_keeps_uncertain_scope_and_queues_contact_research(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'finalize.db'}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        campaign = Campaign(
            campaign_id="campaign-company-finalize",
            name="Companies",
            campaign_type="initiative_outreach",
            status="researching",
            brief_json=json.dumps({"role_focus": "Applied AI", "locations": ["Konstanz"], "max_companies": 10}),
        )
        session.add(campaign)
        session.flush()
        payload = compile_research_plan(campaign, schema_path=SCHEMA)
        plan = replace_pending_plan(session, campaign, payload)
        confirm_plan(plan)
        target = session.exec(select(ResearchTarget).where(ResearchTarget.research_plan_id == plan.id)).one()
        target.status = "covered"
        company = Company(
            company_id="company-balanced",
            name="Balanced GmbH",
            normalized_name="balanced gmbh",
            company_policy_key="balanced.example",
            company_policy_key_kind="domain",
            normalized_domain="balanced.example",
            locations_json=json.dumps(["Lake Constance region"]),
            confidence=0.8,
            raw_json="{}",
        )
        session.add_all([plan, target, company])
        session.flush()
        session.add(
            ResearchDiscovery(
                campaign_id=campaign.id,
                target_id=target.id,
                candidate_kind="company",
                candidate_external_id=company.company_id,
                run_id="run-balanced",
            )
        )
        session.commit()

        WorkflowEngine(session)._maybe_finalize_balanced_campaign(campaign)
        session.commit()

        session.refresh(plan)
        session.refresh(campaign)
        link = session.exec(select(CampaignCompany).where(CampaignCompany.campaign_id == campaign.id)).one()
        task = session.exec(select(AgentTask).where(AgentTask.campaign_id == campaign.id)).one()
        assert plan.status == "completed"
        assert campaign.status == "preparing"
        assert "needs review" in (link.stage_reason or "")
        assert task.task_type == "contact_research"


def test_balanced_job_research_finalization_audits_conflicts_and_links_retained_jobs(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'job-finalize.db'}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        campaign = Campaign(
            campaign_id="campaign-job-finalize",
            name="Jobs",
            campaign_type="listed_job_search",
            status="researching",
            brief_json=json.dumps(
                {"role_focus": "Applied AI", "locations": ["Remote"], "max_jobs": 10}
            ),
        )
        session.add(campaign)
        session.flush()
        payload = compile_research_plan(campaign, schema_path=SCHEMA)
        plan = replace_pending_plan(session, campaign, payload)
        confirm_plan(plan)
        target = session.exec(
            select(ResearchTarget).where(ResearchTarget.research_plan_id == plan.id)
        ).one()
        target.status = "covered"
        retained = JobPosting(
            job_id="job-remote-europe",
            external_company_id="company-retained",
            title="Applied AI Engineer",
            source_url="https://example.com/jobs/retained",
            canonical_url="https://example.com/jobs/retained",
            application_url="https://example.com/jobs/retained/apply",
            source_domain="example.com",
            source_kind="employer_career_page",
            fingerprint="retained",
            work_mode="fully_remote",
            remote_regions_json=json.dumps(["Europe"]),
            vacancy_status="verified_open",
            confidence=0.9,
        )
        excluded = JobPosting(
            job_id="job-remote-us",
            external_company_id="company-excluded",
            title="Applied AI Engineer, US",
            source_url="https://example.org/jobs/excluded",
            canonical_url="https://example.org/jobs/excluded",
            application_url="https://example.org/jobs/excluded/apply",
            source_domain="example.org",
            source_kind="employer_career_page",
            fingerprint="excluded",
            work_mode="fully_remote",
            remote_regions_json=json.dumps(["United States"]),
            vacancy_status="verified_open",
            confidence=0.9,
        )
        session.add_all([plan, target, retained, excluded])
        session.flush()
        session.add_all(
            [
                ResearchDiscovery(
                    campaign_id=campaign.id,
                    target_id=target.id,
                    candidate_kind="job",
                    candidate_external_id=job.job_id,
                    run_id="run-balanced-jobs",
                )
                for job in (retained, excluded)
            ]
        )
        session.commit()

        WorkflowEngine(session)._maybe_finalize_balanced_campaign(campaign)
        session.commit()

        session.refresh(plan)
        session.refresh(campaign)
        links = session.exec(
            select(CampaignJob).where(CampaignJob.campaign_id == campaign.id)
        ).all()
        audit = session.exec(
            select(AuditLog).where(
                AuditLog.action == "research_candidate_excluded",
                AuditLog.entity_id == excluded.job_id,
            )
        ).one()
        assert plan.status == "completed"
        assert campaign.status == "active"
        assert [link.job_posting_id for link in links] == [retained.id]
        assert audit.result_status == "excluded"
        assert json.loads(audit.reason_codes_json) == ["remote_region_conflict"]


def test_geographic_target_counts_only_confirmed_matches_and_keeps_review_candidates_visible(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'geographic-target.db'}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        campaign = Campaign(
            campaign_id="campaign-geographic-target",
            name="Konstanz jobs",
            campaign_type="listed_job_search",
            status="researching",
            brief_json=json.dumps(
                {"role_focus": "Applied AI", "locations": ["Konstanz"], "max_jobs": 10}
            ),
        )
        session.add(campaign)
        session.flush()
        payload = compile_research_plan(campaign, schema_path=SCHEMA)
        plan = replace_pending_plan(session, campaign, payload)
        confirm_plan(plan)
        target = session.exec(
            select(ResearchTarget).where(ResearchTarget.research_plan_id == plan.id)
        ).one()
        target.status = "exhausted"
        target.completed_attempts = target.required_attempts
        matching = JobPosting(
            job_id="job-konstanz",
            external_company_id="company-konstanz",
            title="AI Engineer",
            source_url="https://example.com/jobs/konstanz",
            canonical_url="https://example.com/jobs/konstanz",
            application_url="https://example.com/jobs/konstanz/apply",
            source_domain="example.com",
            source_kind="employer_career_page",
            fingerprint="konstanz",
            locations_json=json.dumps(["Konstanz, Germany"]),
            vacancy_status="verified_open",
            confidence=0.9,
        )
        review = JobPosting(
            job_id="job-reutlingen",
            external_company_id="company-reutlingen",
            title="ML Engineer",
            source_url="https://example.org/jobs/reutlingen",
            canonical_url="https://example.org/jobs/reutlingen",
            application_url="https://example.org/jobs/reutlingen/apply",
            source_domain="example.org",
            source_kind="employer_career_page",
            fingerprint="reutlingen",
            locations_json=json.dumps(["Reutlingen, Germany"]),
            vacancy_status="verified_open",
            confidence=0.9,
        )
        session.add_all([plan, target, matching, review])
        session.flush()
        session.add_all(
            [
                ResearchDiscovery(
                    campaign_id=campaign.id,
                    target_id=target.id,
                    candidate_kind="job",
                    candidate_external_id=job.job_id,
                    run_id="run-geographic-target",
                )
                for job in (matching, review)
            ]
        )
        session.commit()

        workflow = WorkflowEngine(session)
        target.candidate_count = workflow._assess_target_discoveries(
            target,
            candidate_kind="job",
        )
        session.add(target)
        session.commit()

        discoveries = session.exec(
            select(ResearchDiscovery).where(ResearchDiscovery.target_id == target.id)
        ).all()
        assert target.candidate_count == 1
        assert {
            item.candidate_external_id: item.scope_status for item in discoveries
        } == {
            matching.job_id: "match",
            review.job_id: "needs_review",
        }
        assert workflow._target_coverage_complete(target, target.completed_attempts) is False

        workflow._maybe_finalize_balanced_campaign(campaign)
        session.commit()
        session.refresh(target)

        links = session.exec(
            select(CampaignJob).where(CampaignJob.campaign_id == campaign.id)
        ).all()
        assert {link.job_posting_id for link in links} == {matching.id, review.id}
        assert target.retained_count == 1


@pytest.mark.parametrize(
    ("campaign_type", "task_type"),
    [
        ("initiative_outreach", "company_research_target"),
        ("listed_job_search", "job_research_target"),
    ],
)
def test_shared_budget_followups_are_supported_for_both_research_types(tmp_path, campaign_type, task_type):
    engine = create_engine(f"sqlite:///{tmp_path / f'{campaign_type}.db'}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        campaign = Campaign(
            campaign_id=f"campaign-{campaign_type}",
            name="Shared pool",
            campaign_type=campaign_type,
            status="researching",
            brief_json=json.dumps(
                {
                    "role_focus": "Applied AI",
                    "locations": ["Zurich", "Basel"],
                    "search_breadth": "balanced",
                    "max_companies": 30,
                    "max_jobs": 30,
                    "time_budget_minutes": 30,
                }
            ),
        )
        session.add(campaign)
        session.flush()
        payload = compile_research_plan(campaign, schema_path=SCHEMA)
        plan = replace_pending_plan(session, campaign, payload)
        confirm_plan(plan)
        targets = session.exec(select(ResearchTarget).where(ResearchTarget.research_plan_id == plan.id)).all()
        for target in targets:
            target.status = "covered"
            target.completed_attempts = target.required_attempts
            target.consumed_time_seconds = 60
            target.reserved_time_seconds = 0
            session.add(target)
        session.add(plan)
        session.commit()

        assert WorkflowEngine(session)._maybe_schedule_shared_research(campaign) is True
        session.commit()

        tasks = session.exec(select(AgentTask).where(AgentTask.campaign_id == campaign.id)).all()
        assert len(tasks) == 2
        assert {task.task_type for task in tasks} == {task_type}
        assert all(json.loads(task.input_json)["budget_phase"] == "shared" for task in tasks)
        assert all(json.loads(task.input_json)["candidate_goal"] == 2 for task in tasks)
        assert all(json.loads(task.input_json)["time_budget_seconds"] == 120 for task in tasks)
