# Product Specification

## Purpose

Build a personal, local-first application that helps a user run initiative job outreach with high transparency and safety.

The system should find relevant companies, evaluate fit, tailor CV materials from verified profile data, draft personal outreach emails, create structured send intents, and track all outreach and responses.

## Primary User

One local user who wants to run proactive job applications without losing control over identity, factual claims, targeting constraints, or email sending.

## Product Goals

- Make autonomous outreach inspectable through a dashboard.
- Keep personal data and outreach state local by default.
- Separate creative LLM work from deterministic program decisions.
- Prevent duplicate, policy-violating, unsupported, or low-confidence outreach.
- Support dry-run workflows first, then controlled sending later.

## Non-Goals for the Foundation

- No Gmail sending implementation.
- No OpenAI API dependency.
- No full frontend or backend implementation.
- No enterprise multi-user permission model.
- No hardcoded global moral exclusions.

## Core Workflows

1. Onboarding collects the user's career data, preferences, constraints, tone, and exclusion criteria.
2. Company research creates `company_candidate.json` files with sources and confidence.
3. Contact research creates `contact_candidate.json` files with evidence and review flags.
4. Fit evaluation creates `fit_evaluation.json` files using the profile and policy.
5. CV tailoring creates draft CV artifacts from `master_cv_profile.json` only.
6. Email drafting creates `email_draft.json` files with sourced personalization.
7. Send intent creation creates `send_intent.json` files.
8. Backend import validates outputs, stores them, and displays them in the dashboard.
9. Backend send gate decides whether an intent is eligible for dry-run approval or future sending.

## Dashboard Requirements

The frontend should show:

- Runs and their status.
- Companies found, evaluated, accepted, rejected, blocked, or needing review.
- Contacts found and source quality.
- Draft emails and CV artifacts.
- Send queue with gate status.
- Sent emails and blocked intents.
- Audit log entries before and after every important action.
- Settings for user policy, limits, blocked domains, and dry-run mode.

## Success Criteria

- A user can inspect what agents did and why.
- Duplicate outreach is blocked by database constraints and deterministic gate logic.
- The backend can explain every send or block decision.
- Agent outputs are structured, source-backed, and schema validated.
- The system can evolve toward autonomous sending without changing the core safety boundary.

