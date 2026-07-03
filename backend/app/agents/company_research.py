from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CompanyResearchCampaign:
    run_id: str
    role_focus: str
    locations: list[str]
    time_budget_minutes: int
    max_companies: int
    notes: str | None = None


COMPANY_RESEARCH_INSTRUCTIONS = """# Company Research Agent

You are researching companies for a local-first job outreach system.

Hard boundaries:

- Write only JSON files under `output/`.
- Do not send email or contact anyone.
- Do not create send intents or email drafts in this run.
- Do not use Gmail, SMTP, email APIs, contact forms, messaging services, or outreach tools.
- Use only the approved profile, master CV, policy, schemas, and campaign brief in `input/`.
- Use Playwright-backed browsing from the scoped shell only for public company, search, funding, hiring, product, and job-page research.
- Preserve source references for every factual claim.
- Mark uncertainty with lower confidence and `review_flags`; do not rely on manual user approval to make weak evidence safe.
- Read `input/existing_companies.json` before researching and avoid companies whose name, domain, normalized name, or policy key already appears there.
- While researching each company, attempt to find a public professional careers, recruiting, HR, jobs, or talent contact email address.
- Prefer role-neutral company-listed addresses such as careers@, jobs@, recruiting@, talent@, hr@, or a public careers-team address.
- Do not scrape private personal emails, guess individual employee emails, submit forms, or message anyone.
- Generic company addresses such as careers@, jobs@, recruiting@, talent@, hr@, info@, or contact@ are acceptable when public and valid.
- If an address is inferred, weakly sourced, stale, or ambiguous, lower confidence and add remediation review flags so a later contact-research pass can try to replace it.
- Treat remote, hybrid, and onsite as acceptable when the approved user profile says so. Record remote or office policy when it is readily available, but do not spend disproportionate time proving remote availability and do not mark unknown remote policy as a risk by itself.
- Only flag location or work-mode risk when there is evidence of an actual conflict, such as a required location, relocation, travel pattern, or onsite policy outside the approved target locations or stated preferences.

This campaign writes JSON files for each company, any public career contact found, and fit evaluation:

- `output/companies/<stable-company-id>.json`
- `output/contacts/<stable-contact-id>.json`
- `output/fit_evaluations/<stable-evaluation-id>.json`

The backend will validate and import these files before they appear in the dashboard.
"""


def build_company_research_task(campaign: CompanyResearchCampaign) -> str:
    brief = {
        "run_id": campaign.run_id,
        "role_focus": campaign.role_focus,
        "locations": campaign.locations,
        "time_budget_minutes": campaign.time_budget_minutes,
        "max_companies": campaign.max_companies,
        "notes": campaign.notes or "",
    }
    target_text = f"{campaign.max_companies} company candidates"
    return (
        "# Company Research Campaign\n\n"
        f"Research up to {target_text} within about {campaign.time_budget_minutes} minutes and evaluate each fit.\n\n"
        "Campaign brief:\n\n"
        f"```json\n{json.dumps(brief, indent=2, sort_keys=True)}\n```\n\n"
        "Use `../input/user_profile.json`, `../input/master_cv_profile.json`, and `../input/policy.json` as approved context.\n"
        "Use `../input/existing_companies.json` as a do-not-duplicate list. Do not spend research time on companies already listed there, "
        "unless the campaign notes explicitly ask for a refresh of an existing company.\n"
        "Use `../input/schemas/company_candidate.schema.json`, `../input/schemas/contact_candidate.schema.json`, "
        "and `../input/schemas/fit_evaluation.schema.json` for exact output shape.\n\n"
        "Output requirements:\n\n"
        "- Write company candidates to `../output/companies/<stable-company-id>.json`.\n"
        "- Write public career contact candidates to `../output/contacts/<stable-contact-id>.json` when a usable address is found.\n"
        "- Write fit evaluations to `../output/fit_evaluations/<stable-evaluation-id>.json`.\n"
        "- Each company candidate must identify the company, domain, description, locations, source refs, confidence, and review flags.\n"
        "- Each contact candidate must reference the same `company_id`, preserve source refs, and classify the email source.\n"
        "- Prefer company-published career contact addresses over individual people; generic company addresses are acceptable when public and valid. If no public address is found, omit the contact file instead of inventing one.\n"
        "- Each fit evaluation must reference the same `company_id`, the approved profile ID, and the approved policy ID.\n"
        "- Use the approved user profile and campaign brief for target locations; do not require currently open job listings before recording an interesting company.\n"
        "- Remote policy is descriptive metadata, not a hard requirement when the profile allows hybrid or onsite. Do not add a risk just because remote policy is unverified.\n"
        f"- Keep researching until either {target_text} have been written or the time budget is exhausted. Do not stop after a small first batch.\n"
        "- If obvious leads run thin, broaden discovery sources and search angles before stopping: company directories, startup ecosystems, funding/news pages, product categories, hiring pages, and local employer lists.\n"
        "- Build a candidate backlog first, then write company and fit files for the strongest new non-duplicate companies. Contact files are optional when no public professional email is found.\n"
        "- Every reason and risk must cite source refs.\n"
        "- If evidence is weak, keep the record reviewable instead of overstating confidence.\n"
        "- Do not write drafts, send intents, gate results, Gmail data, SMTP output, or outreach instructions.\n"
    )


def build_company_research_inputs(
    *,
    user_profile: dict[str, Any],
    master_cv_profile: dict[str, Any],
    policy: dict[str, Any],
    company_schema: str,
    contact_schema: str,
    fit_schema: str,
    campaign: CompanyResearchCampaign,
    existing_companies: list[dict[str, Any]] | None = None,
) -> dict[str, str]:
    return {
        "campaign.json": json.dumps(
            {
                "run_id": campaign.run_id,
                "role_focus": campaign.role_focus,
                "locations": campaign.locations,
                "time_budget_minutes": campaign.time_budget_minutes,
                "max_companies": campaign.max_companies,
                "notes": campaign.notes or "",
            },
            indent=2,
            sort_keys=True,
        ),
        "existing_companies.json": json.dumps(
            {
                "schema_version": "1.0",
                "profile_id": user_profile.get("profile_id"),
                "description": "Companies already discovered for this user profile. Avoid researching or rewriting these companies in this run.",
                "companies": existing_companies or [],
            },
            indent=2,
            sort_keys=True,
        ),
        "user_profile.json": json.dumps(user_profile, indent=2, sort_keys=True),
        "master_cv_profile.json": json.dumps(master_cv_profile, indent=2, sort_keys=True),
        "policy.json": json.dumps(policy, indent=2, sort_keys=True),
        "schemas/company_candidate.schema.json": company_schema,
        "schemas/contact_candidate.schema.json": contact_schema,
        "schemas/fit_evaluation.schema.json": fit_schema,
    }
