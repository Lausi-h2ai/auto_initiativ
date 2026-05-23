from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CompanyResearchCampaign:
    run_id: str
    role_focus: str
    locations: list[str]
    max_companies: int
    notes: str | None = None


COMPANY_RESEARCH_INSTRUCTIONS = """# Company Research Agent

You are researching companies for a local-first job outreach system.

Hard boundaries:

- Write only JSON files under `output/`.
- Do not send email or contact anyone.
- Do not create send intents, email drafts, or contact candidates in this run.
- Use only the approved profile, master CV, policy, schemas, and campaign brief in `input/`.
- Preserve source references for every factual claim.
- Mark uncertainty with lower confidence and `review_flags`.

This first campaign run writes exactly:

- `output/company_candidate.json`
- `output/fit_evaluation.json`

The backend will validate and import these files before they appear in the dashboard.
"""


def build_company_research_task(campaign: CompanyResearchCampaign) -> str:
    brief = {
        "run_id": campaign.run_id,
        "role_focus": campaign.role_focus,
        "locations": campaign.locations,
        "max_companies": campaign.max_companies,
        "notes": campaign.notes or "",
    }
    return (
        "# Company Research Campaign\n\n"
        "Find one high-quality company candidate for this first campaign slice and evaluate its fit.\n\n"
        "Campaign brief:\n\n"
        f"```json\n{json.dumps(brief, indent=2, sort_keys=True)}\n```\n\n"
        "Use `input/user_profile.json`, `input/master_cv_profile.json`, and `input/policy.json` as approved context.\n"
        "Use `input/schemas/company_candidate.schema.json` and `input/schemas/fit_evaluation.schema.json` for exact output shape.\n\n"
        "Output requirements:\n\n"
        "- `company_candidate.json` must identify the company, domain, description, locations, source refs, confidence, and review flags.\n"
        "- `fit_evaluation.json` must reference the same `company_id`, the approved profile ID, and the approved policy ID.\n"
        "- Every reason and risk must cite source refs.\n"
        "- If evidence is weak, keep the record reviewable instead of overstating confidence.\n"
    )


def build_company_research_inputs(
    *,
    user_profile: dict[str, Any],
    master_cv_profile: dict[str, Any],
    policy: dict[str, Any],
    company_schema: str,
    fit_schema: str,
    campaign: CompanyResearchCampaign,
) -> dict[str, str]:
    return {
        "campaign.json": json.dumps(
            {
                "run_id": campaign.run_id,
                "role_focus": campaign.role_focus,
                "locations": campaign.locations,
                "max_companies": campaign.max_companies,
                "notes": campaign.notes or "",
            },
            indent=2,
            sort_keys=True,
        ),
        "user_profile.json": json.dumps(user_profile, indent=2, sort_keys=True),
        "master_cv_profile.json": json.dumps(master_cv_profile, indent=2, sort_keys=True),
        "policy.json": json.dumps(policy, indent=2, sort_keys=True),
        "schemas/company_candidate.schema.json": company_schema,
        "schemas/fit_evaluation.schema.json": fit_schema,
    }
