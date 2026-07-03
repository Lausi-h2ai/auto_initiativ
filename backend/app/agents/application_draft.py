from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any


APPLICATION_DRAFT_INSTRUCTIONS = """# Application Draft Agent

You are creating one tailored unsolicited application package for a local-first job outreach system.

Hard boundaries:

- Do not send email or contact anyone.
- Do not use Gmail, mail APIs, contact forms, messaging services, credentials, or secrets.
- Do not create `send_intent.json`, gate results, reservations, outreach records, or delivery state.
- Start from `../input/draft_context.json`; read larger inputs only when needed to produce the requested artifacts.
- Do not perform contact research unless `../input/application_draft.json` explicitly sets `contact_needs_research` to true. If contact data is missing or uncertain in normal drafting runs, mark the draft with remediation flags instead of browsing or guessing.
- Future CV tailoring may only use claims from the approved master CV profile. Do not invent experience, dates, education, skills, credentials, achievements, or personal facts.
- If a useful claim is missing or ambiguous, omit it or add a review flag. Do not fill gaps by guessing.
- Keep the resume to one page.
- Write only `../output/email_draft.json`, `../output/contact_candidate.json` when explicitly required, and files under `../output/attachments`.
- The backend will validate `email_draft.json` and serve attachments for backend-controlled evaluation. It will not send anything from this run.

Use the compact tone and workflow notes in `../input/draft_context.json`. Use the master CV HTML in `../input/master_cv/de_ch_master.html` as the real starting point for the tailored CV.
On this machine, render the CV PDF with `application_draft_render_pdf` after writing the HTML attachment. Do not use WeasyPrint unless the render tool is unavailable.
The tailored resume must remain real HTML text rendered to PDF; do not create image-only, screenshot, canvas, PIL, ReportLab, or rasterized resume PDFs.
"""

REDACTED_RESUME_PHRASES = ("Summa Cum Laude",)


@dataclass(frozen=True)
class ApplicationDraftBrief:
    run_id: str
    draft_id: str
    company_id: str
    contact_id: str
    company_slug: str
    contact_needs_research: bool = False
    language: str | None = None
    notes: str | None = None

    @property
    def html_filename(self) -> str:
        return f"{self.company_slug}-lebenslauf.html"

    @property
    def pdf_filename(self) -> str:
        return f"{self.company_slug}-lebenslauf.pdf"


def slugify(value: str, *, fallback: str = "company") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:80] or fallback


def _redact_resume_text(value: str) -> str:
    redacted = value
    for phrase in REDACTED_RESUME_PHRASES:
        redacted = re.sub(rf"\s*\|\s*{re.escape(phrase)}", "", redacted, flags=re.IGNORECASE)
        redacted = re.sub(rf"{re.escape(phrase)}\s*\|\s*", "", redacted, flags=re.IGNORECASE)
        redacted = re.sub(re.escape(phrase), "", redacted, flags=re.IGNORECASE)
    redacted = re.sub(r"\s+\|", " |", redacted)
    redacted = re.sub(r"\|\s+\|", "|", redacted)
    return redacted


def _redact_resume_data(value: Any) -> Any:
    if isinstance(value, str):
        return _redact_resume_text(value)
    if isinstance(value, list):
        return [_redact_resume_data(item) for item in value]
    if isinstance(value, dict):
        return {key: _redact_resume_data(item) for key, item in value.items()}
    return value


def _source_refs(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return []
    refs = value.get("source_refs")
    if isinstance(refs, list):
        return [str(item) for item in refs if isinstance(item, str) and item]
    provenance = value.get("provenance")
    if isinstance(provenance, dict):
        refs = provenance.get("source_refs")
        if isinstance(refs, list):
            return [str(item) for item in refs if isinstance(item, str) and item]
    return []


def _compact_text(value: Any, *, max_length: int = 500) -> str | None:
    if not isinstance(value, str):
        return None
    text = re.sub(r"\s+", " ", _redact_resume_text(value)).strip()
    if not text:
        return None
    return text if len(text) <= max_length else f"{text[: max_length - 1].rstrip()}..."


def _claim_text(claim: dict[str, Any]) -> str | None:
    for key in ("statement", "text", "value", "summary", "description", "title"):
        text = _compact_text(claim.get(key))
        if text:
            return text
    return None


def _compact_claims(master_cv_profile: dict[str, Any]) -> list[dict[str, Any]]:
    claims = master_cv_profile.get("claims")
    if not isinstance(claims, list):
        return []
    compact: list[dict[str, Any]] = []
    for index, raw_claim in enumerate(claims):
        if not isinstance(raw_claim, dict):
            continue
        claim_id = raw_claim.get("claim_id") or raw_claim.get("id") or raw_claim.get("stable_id")
        text = _claim_text(raw_claim)
        if not isinstance(claim_id, str) or not claim_id or text is None:
            continue
        compact.append(
            {
                "claim_id": claim_id,
                "text": text,
                "source_refs": _source_refs(raw_claim),
                "needs_review": bool(raw_claim.get("needs_review") or raw_claim.get("review_required")),
            }
        )
        if len(compact) >= 80:
            break
    return compact


def _compact_company(company: dict[str, Any]) -> dict[str, Any]:
    return {
        "company_id": company.get("company_id"),
        "name": company.get("name"),
        "domain": company.get("domain") or company.get("website_url") or company.get("raw_domain"),
        "description": _compact_text(company.get("description"), max_length=700),
        "industry_tags": company.get("industry_tags") if isinstance(company.get("industry_tags"), list) else [],
        "locations": company.get("locations") if isinstance(company.get("locations"), list) else [],
        "source_refs": _source_refs(company),
        "review_flags": company.get("review_flags") if isinstance(company.get("review_flags"), list) else [],
    }


def _compact_contact(contact: dict[str, Any]) -> dict[str, Any]:
    return {
        "contact_id": contact.get("contact_id"),
        "name": contact.get("name"),
        "role_title": contact.get("role_title"),
        "email": contact.get("email") or contact.get("raw_email"),
        "email_source": contact.get("email_source"),
        "source_refs": _source_refs(contact),
        "review_flags": contact.get("review_flags") if isinstance(contact.get("review_flags"), list) else [],
        "status": contact.get("status"),
    }


def _compact_fit(fit_evaluation: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(fit_evaluation, dict):
        return {}
    reasons = fit_evaluation.get("reasons")
    risks = fit_evaluation.get("risks")
    return {
        "decision": fit_evaluation.get("decision"),
        "fit_score": fit_evaluation.get("fit_score"),
        "reasons": reasons[:5] if isinstance(reasons, list) else [],
        "risks": risks[:5] if isinstance(risks, list) else [],
        "source_refs": _source_refs(fit_evaluation),
        "review_flags": fit_evaluation.get("review_flags") if isinstance(fit_evaluation.get("review_flags"), list) else [],
    }


def _compact_user_profile(user_profile: dict[str, Any]) -> dict[str, Any]:
    preferences = user_profile.get("preferences") if isinstance(user_profile.get("preferences"), dict) else {}
    return {
        "profile_id": user_profile.get("profile_id"),
        "display_name": (user_profile.get("identity") or {}).get("display_name") if isinstance(user_profile.get("identity"), dict) else None,
        "communication_tone": preferences.get("communication_tone"),
        "target_roles": preferences.get("target_roles") if isinstance(preferences.get("target_roles"), list) else [],
        "target_locations": preferences.get("target_locations") if isinstance(preferences.get("target_locations"), list) else [],
        "work_authorization": user_profile.get("work_authorization") if isinstance(user_profile.get("work_authorization"), list) else [],
        "languages": user_profile.get("languages") if isinstance(user_profile.get("languages"), list) else [],
    }


def build_application_draft_context(
    *,
    brief: ApplicationDraftBrief,
    user_profile: dict[str, Any],
    master_cv_profile: dict[str, Any],
    policy: dict[str, Any],
    company: dict[str, Any],
    contact: dict[str, Any],
    fit_evaluation: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "run": {
            "run_id": brief.run_id,
            "draft_id": brief.draft_id,
            "company_id": brief.company_id,
            "contact_id": brief.contact_id,
            "language": brief.language or "auto",
            "notes": brief.notes or "",
            "outputs": {
                "email_draft": "../output/email_draft.json",
                "cv_html": f"../output/attachments/{brief.html_filename}",
                "cv_pdf": f"../output/attachments/{brief.pdf_filename}",
                "cv_attachment_path": f"attachments/{brief.pdf_filename}",
                "cv_attachment_id": f"cv-{brief.company_slug}",
            },
        },
        "workflow": {
            "read_order": [
                "draft_context.json",
                "master_cv/de_ch_master.html only when writing the tailored HTML",
                "schemas/email_draft.schema.json only if needed for JSON shape",
            ],
            "no_contact_research": not brief.contact_needs_research,
            "max_pdf_render_attempts": 1,
            "mark_review_instead_of_browsing": True,
            "tone": "direct, professional, concise, personal enough to avoid generic corporate filler",
        },
        "user_profile": _compact_user_profile(user_profile),
        "policy": {
            "policy_id": policy.get("policy_id"),
            "blocked_domains": policy.get("blocked_domains") if isinstance(policy.get("blocked_domains"), list) else [],
            "notes": _compact_text(policy.get("notes"), max_length=500),
        },
        "company": _compact_company(company),
        "contact": _compact_contact(contact),
        "fit_evaluation": _compact_fit(fit_evaluation),
        "approved_claims": _compact_claims(master_cv_profile),
    }


def build_application_draft_task(brief: ApplicationDraftBrief) -> str:
    payload = {
        "run_id": brief.run_id,
        "draft_id": brief.draft_id,
        "company_id": brief.company_id,
        "contact_id": brief.contact_id,
        "contact_needs_research": brief.contact_needs_research,
        "language": brief.language or "auto",
        "notes": brief.notes or "",
        "outputs": {
            "email_draft": "../output/email_draft.json",
            "contact_candidate": "../output/contact_candidate.json" if brief.contact_needs_research else None,
            "cv_html": f"../output/attachments/{brief.html_filename}",
            "cv_pdf": f"../output/attachments/{brief.pdf_filename}",
            "cv_attachment_path": f"attachments/{brief.pdf_filename}",
            "cv_attachment_id": f"cv-{brief.company_slug}",
        },
    }
    return (
        "# Application Draft Task\n\n"
        "Create one tailored CV PDF and one email draft for the selected company/contact.\n\n"
        "Brief:\n\n"
        f"```json\n{json.dumps(payload, indent=2, sort_keys=True)}\n```\n\n"
        "Required process:\n\n"
        "1. Read `../input/draft_context.json` first and use it as the compact source of truth for the run.\n"
        "2. Decide which approved claim IDs from `approved_claims` best match the company and fit evaluation.\n"
        "3. Tailor the CV HTML from `../input/master_cv/de_ch_master.html`; preserve readable proportions and rework only approved claims. Read the full HTML only when writing the tailored attachment.\n"
        f"4. Write the tailored HTML to `../output/attachments/{brief.html_filename}`. This HTML source is required.\n"
        "5. Render that HTML text document to a one-page PDF under `../output/attachments` using `application_draft_render_pdf`, and verify the PDF exists before finishing. Try at most one repair if rendering fails.\n"
        "6. Do not render the resume as a screenshot, bitmap, canvas, PIL image, ReportLab drawing, or image-only PDF. Text in the PDF must remain readable and selectable.\n"
        + (
            "7. If `contact_needs_research` is true, find one public professional contact email and write `../output/contact_candidate.json`; keep shell/web output tiny and never dump raw search pages.\n"
            if brief.contact_needs_research
            else "7. Do not research contacts in this run. If contact context is missing or weak, add review flags to `email_draft.json`.\n"
        )
        + "8. Write `../output/email_draft.json` matching `../input/schemas/email_draft.schema.json`.\n\n"
        + (
            "Contact research requirements:\n\n"
            "- Use the selected `contact_id` exactly in `contact_candidate.json` when contact research is required.\n"
            "- Prefer emails published on the company site or a public professional profile.\n"
            "- Do not use private personal emails, guessed emails, contact forms, Gmail, mail APIs, or messaging services.\n"
            "- Generic company addresses such as careers@, jobs@, recruiting@, talent@, hr@, info@, or contact@ are acceptable when public and valid; keep the email draft general.\n"
            "- If the best available email is inferred or weakly sourced, add remediation review flags and lower confidence so a later contact-research pass can try to replace it.\n"
            "- Never return full HTML/search-result pages to the model; extract only the email, URL, and one short evidence snippet.\n\n"
            if brief.contact_needs_research
            else ""
        )
        + "Email draft requirements:\n\n"
        "- Use the selected `draft_id`, `company_id`, and `contact_id` exactly.\n"
        "- Reference the CV PDF with attachment "
        f"`{{ \"attachment_id\": \"cv-{brief.company_slug}\", \"path\": \"attachments/{brief.pdf_filename}\", \"kind\": \"cv\" }}`.\n"
        "- Use concrete company evidence and approved claim IDs in `claim_refs` and `source_refs`.\n"
        "- Mark `review_flags` when the recipient, language, claim fit, PDF rendering, or source evidence needs agent remediation.\n"
        "- Do not mention that the CV was tailored by an agent or that this is a bulk outreach workflow.\n"
        "- Never include the phrase `Summa Cum Laude` in the resume or email draft.\n\n"
        "Resume layout requirements:\n\n"
        "- Use the available one-page space well; do not leave a visibly sparse lower third when relevant approved content exists.\n"
        "- If the rendered PDF has substantial blank space, add or restore relevant approved bullets, skills, project details, or education detail before finishing.\n"
        "- Keep the PDF exactly one page and avoid cramped or tiny text.\n"
        "- Use normal A4 CSS proportions: roughly 8-12mm page margins, body text around 9-10pt, section headings around 9-11pt, and a portrait photo around 30-35mm wide.\n"
        "- Do not use global CSS transforms, zoom, fixed 2000px+ canvases, raster text, or bitmap page rendering to make content fit.\n"
    )


def build_application_draft_inputs(
    *,
    brief: ApplicationDraftBrief,
    user_profile: dict[str, Any],
    master_cv_profile: dict[str, Any],
    policy: dict[str, Any],
    company: dict[str, Any],
    contact: dict[str, Any],
    fit_evaluation: dict[str, Any] | None,
    email_draft_schema: str,
    contact_schema: str,
    master_cv_html: str,
    handoff_docs: dict[str, str],
) -> dict[str, str]:
    safe_master_cv_profile = _redact_resume_data(master_cv_profile)
    safe_master_cv_html = _redact_resume_text(master_cv_html)
    draft_context = build_application_draft_context(
        brief=brief,
        user_profile=user_profile,
        master_cv_profile=safe_master_cv_profile,
        policy=policy,
        company=company,
        contact=contact,
        fit_evaluation=fit_evaluation,
    )
    return {
        "draft_context.json": json.dumps(draft_context, indent=2, sort_keys=True),
        "application_draft.json": json.dumps(
            {
                "run_id": brief.run_id,
                "draft_id": brief.draft_id,
                "company_id": brief.company_id,
                "contact_id": brief.contact_id,
                "contact_needs_research": brief.contact_needs_research,
                "company_slug": brief.company_slug,
                "language": brief.language or "auto",
                "notes": brief.notes or "",
                "outputs": {
                    "email_draft": "../output/email_draft.json",
                    "contact_candidate": "../output/contact_candidate.json" if brief.contact_needs_research else None,
                    "cv_html": f"../output/attachments/{brief.html_filename}",
                    "cv_pdf": f"../output/attachments/{brief.pdf_filename}",
                    "cv_attachment_path": f"attachments/{brief.pdf_filename}",
                    "cv_attachment_id": f"cv-{brief.company_slug}",
                },
            },
            indent=2,
            sort_keys=True,
        ),
        "company.json": json.dumps(company, indent=2, sort_keys=True),
        "contact.json": json.dumps(contact, indent=2, sort_keys=True),
        "fit_evaluation.json": json.dumps(fit_evaluation or {}, indent=2, sort_keys=True),
        "user_profile.json": json.dumps(user_profile, indent=2, sort_keys=True),
        "master_cv_profile.json": json.dumps(safe_master_cv_profile, indent=2, sort_keys=True),
        "policy.json": json.dumps(policy, indent=2, sort_keys=True),
        "schemas/email_draft.schema.json": email_draft_schema,
        **({"schemas/contact_candidate.schema.json": contact_schema} if brief.contact_needs_research else {}),
        "master_cv/de_ch_master.html": safe_master_cv_html,
        **{f"handoff/{name}": content for name, content in sorted(handoff_docs.items())},
    }
