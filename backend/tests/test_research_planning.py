from __future__ import annotations

import json
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine, select

from backend.app.db.models import (
    AgentTask,
    Campaign,
    CampaignCompany,
    Company,
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
