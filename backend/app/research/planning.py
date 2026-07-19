from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from jsonschema import Draft202012Validator, FormatChecker
from sqlmodel import Session, select

from backend.app.db.models import Campaign, ResearchPlan, ResearchTarget, utc_now


DEFAULT_REQUIRED_ATTEMPTS = 3
REMOTE_TOKENS = {"remote", "fully remote", "100% remote", "full remote"}


def _fold(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return " ".join("".join(char for char in normalized if not unicodedata.combining(char)).casefold().split())


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", _fold(value)).strip("-")
    return slug or "target"


def _duration_constraint(text: str) -> dict[str, Any] | None:
    patterns = (
        r"(?:mindestens|min\.?|at least)\s+(\d+)\s*(?:wochen|weeks?)",
        r"(\d+)\s*(?:wochen|weeks?)\s+(?:minimum|minestens|at least)",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return {
                "key": "minimum_duration_weeks",
                "operator": "at_least",
                "value": int(match.group(1)),
                "source_text": match.group(0),
                "confidence": 0.99,
            }
    return None


def compile_research_plan(campaign: Campaign, *, schema_path: Path) -> dict[str, Any]:
    brief = json.loads(campaign.brief_json or "{}")
    role_focus = str(brief.get("role_focus") or "Profile-aligned roles").strip()
    guidance = str(brief.get("additional_guidance") or brief.get("company_preferences") or "").strip()
    locations = [str(item).strip() for item in brief.get("locations") or [] if str(item).strip()]
    if not locations:
        locations = ["Remote"]

    targets: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for raw in locations:
        folded = _fold(raw)
        if folded in REMOTE_TOKENS:
            kind = "remote"
            label = "Remote Europe"
            normalized = "europe"
            aliases = ["Remote", "Remote Europe", "Europe remote", "fully remote Europe"]
        else:
            kind = "geographic"
            label = raw
            normalized = folded
            aliases = list(dict.fromkeys([raw, folded]))
        dedupe_key = (kind, normalized)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        targets.append(
            {
                "target_id": f"target-{len(targets) + 1:02d}-{_slug(label)}",
                "label": label,
                "kind": kind,
                "normalized_value": normalized,
                "aliases": aliases,
                "required_attempts": DEFAULT_REQUIRED_ATTEMPTS,
            }
        )

    combined = " ".join(part for part in (role_focus, guidance) if part)
    hard_constraints: list[dict[str, Any]] = []
    if re.search(r"\b(pflichtpraktikum|praktikum|internship|intern)\b", combined, re.IGNORECASE):
        hard_constraints.append(
            {
                "key": "employment_type",
                "operator": "includes",
                "value": "internship",
                "source_text": next(
                    match.group(0)
                    for match in re.finditer(r"\b(pflichtpraktikum|praktikum|internship|intern)\b", combined, re.IGNORECASE)
                ),
                "confidence": 0.98,
            }
        )
    duration = _duration_constraint(combined)
    if duration:
        hard_constraints.append(duration)
    if any(target["kind"] == "remote" for target in targets):
        hard_constraints.extend(
            [
                {
                    "key": "work_mode",
                    "operator": "equals",
                    "value": "fully_remote",
                    "source_text": "Remote",
                    "confidence": 1.0,
                },
                {
                    "key": "remote_region",
                    "operator": "equals",
                    "value": "Europe",
                    "source_text": "Remote normalized to Remote Europe",
                    "confidence": 1.0,
                },
            ]
        )

    soft_preferences = (
        [{"text": guidance, "source": "campaign_guidance"}] if guidance else []
    )
    review_flags: list[str] = []
    if guidance and re.search(r"\b(nicht zu weit|nearby|close to|commut)\b", guidance, re.IGNORECASE):
        review_flags.append("vague_distance_preference")

    plan = {
        "schema_version": "1.0",
        "plan_id": f"research-plan-{uuid4()}",
        "campaign_id": campaign.campaign_id,
        "campaign_type": campaign.campaign_type,
        "role_focus": role_focus,
        "additional_guidance": guidance,
        "targets": targets,
        "hard_constraints": hard_constraints,
        "soft_preferences": soft_preferences,
        "review_flags": review_flags,
    }
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(plan)
    return plan


def plan_hash(plan: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(plan, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def replace_pending_plan(session: Session, campaign: Campaign, plan: dict[str, Any]) -> ResearchPlan:
    existing = session.exec(
        select(ResearchPlan).where(ResearchPlan.campaign_id == campaign.id).order_by(ResearchPlan.version.desc())
    ).first()
    version = (existing.version + 1) if existing else 1
    if existing and existing.status == "pending_confirmation":
        existing.status = "superseded"
        existing.updated_at = utc_now()
        session.add(existing)
    record = ResearchPlan(
        plan_id=plan["plan_id"],
        campaign_id=campaign.id,
        version=version,
        status="pending_confirmation",
        content_hash=plan_hash(plan),
        raw_json=json.dumps(plan, sort_keys=True),
        workspace_id=campaign.workspace_id,
    )
    session.add(record)
    session.flush()
    for item in plan["targets"]:
        session.add(
            ResearchTarget(
                research_plan_id=record.id,
                campaign_id=campaign.id,
                target_id=item["target_id"],
                label=item["label"],
                target_kind=item["kind"],
                normalized_value=item["normalized_value"],
                required_attempts=item["required_attempts"],
                workspace_id=campaign.workspace_id,
            )
        )
    campaign.status = "planning"
    campaign.updated_at = utc_now()
    session.add(campaign)
    session.commit()
    session.refresh(record)
    return record


def confirm_plan(record: ResearchPlan) -> None:
    record.status = "confirmed"
    record.confirmed_hash = record.content_hash
    record.confirmed_at = datetime.now(timezone.utc)
    record.updated_at = utc_now()
