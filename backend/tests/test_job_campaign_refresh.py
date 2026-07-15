from __future__ import annotations

import json

from sqlmodel import Session, SQLModel, create_engine, select

from backend.app.db.models import AgentTask, Campaign
from backend.app.product.routes import JobCampaignRefresh, refresh_job_campaign


def test_refresh_updates_scope_and_reuses_active_research_task(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'refresh.db'}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        campaign = Campaign(
            campaign_id="campaign-jobs",
            name="Jobs",
            campaign_type="listed_job_search",
            status="researching",
            brief_json=json.dumps(
                {
                    "role_focus": "Administration",
                    "locations": ["Bodenseeregion"],
                    "max_jobs": 30,
                    "freshness_days": 30,
                    "time_budget_minutes": 30,
                }
            ),
        )
        session.add(campaign)
        session.flush()
        task = AgentTask(
            task_id="task-existing",
            campaign_id=campaign.id,
            agent_role="vacancy_scout",
            task_type="job_research",
            status="running",
        )
        session.add(task)
        session.commit()

        result = refresh_job_campaign(
            campaign.campaign_id,
            JobCampaignRefresh(
                role_focus="Public administration and NGO entry roles",
                locations=["Switzerland", "Lake Constance region"],
                max_jobs=40,
            ),
            session,
        )

        session.refresh(campaign)
        brief = json.loads(campaign.brief_json)
        tasks = session.exec(select(AgentTask).where(AgentTask.campaign_id == campaign.id)).all()
        assert result == {"campaign_id": campaign.campaign_id, "task_id": task.task_id, "status": "running"}
        assert brief["locations"] == ["Switzerland", "Lake Constance region"]
        assert brief["role_focus"] == "Public administration and NGO entry roles"
        assert brief["max_jobs"] == 40
        assert len(tasks) == 1
