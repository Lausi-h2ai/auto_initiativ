# Product Specification

## Purpose

Build a personal, local-first application that helps a user run initiative job outreach with high transparency and safety.

The product also supports a parallel `listed_job_search` campaign. It discovers real vacancies, verifies their public application route and freshness, evaluates both employer and role fit, and prepares claim-grounded application materials. It never replaces or merges the initiative-outreach path.

Job applications remain manual-submit: the backend may prepare a tailored CV claim selection, cover letter, and answer kit, but neither an agent nor the backend submits an application form.

The system should find relevant companies, evaluate fit, tailor CV materials from verified profile data, draft personal outreach emails, create structured send intents, and track all outreach and responses.

## Primary User

A user in a private local-first workspace who wants to run proactive job applications without losing control over identity, factual claims, targeting constraints, or email sending. Local account switching and authenticated multi-user deployments preserve workspace isolation.

## Product Goals

- Make autonomous outreach inspectable through a dashboard.
- Keep personal data and outreach state local by default.
- Separate creative LLM work from deterministic program decisions.
- Prevent duplicate, policy-violating, unsupported, or low-confidence outreach.
- Support dry-run workflows first, then controlled sending later.

## Historical Foundation Non-Goals

- No Gmail sending implementation in the original foundation phase.
- No OpenAI API dependency.
- No full frontend or backend implementation in the original foundation phase.
- No enterprise multi-user permission model.
- No hardcoded global moral exclusions.

## Core Workflows

1. Onboarding collects the user's career data, preferences, constraints, tone, and exclusion criteria.
2. A new campaign compiles its role, ordered locations, and additional search guidance into a versioned research plan. The user confirms that interpretation before research starts.
3. Company research creates `company_candidate.json` files with sources and confidence.
4. Contact research creates `contact_candidate.json` files with evidence and review flags.
5. Fit evaluation creates `fit_evaluation.json` files using the profile and policy.
6. CV tailoring creates draft CV artifacts from approved claim IDs in an immutable `master_cv_profile.json` snapshot only.
7. Email drafting creates `email_draft.json` files with sourced personalization.
8. Send intent creation creates `send_intent.json` files.
9. Backend import validates outputs, stores them, and displays them in the dashboard.
10. The backend send gate decides whether an intent is eligible for dry-run approval or controlled backend delivery.

## Controlled Email Delivery

- Email delivery is disabled by default.
- Agents never receive credentials, invoke an adapter, approve work, reserve sends, or decide whether delivery is allowed.
- A backend provider attempt requires schema-valid intent data, an authorized frozen approval, deterministic policy/dedupe/source/claim/attachment/limit checks, and a transactional reservation.
- The backend records pre-attempt and terminal audit checkpoints and distinguishes provider acceptance, known-unsent failure, and uncertain outcomes.
- Local development may use machine-local Gmail credentials only when authentication is disabled. Authenticated deployments require a workspace/user-scoped Gmail connection.
- Listed-job applications remain manual-submit and never use the email-delivery path to submit forms.

Research executes one independently tracked run per confirmed target. Each target receives the same minimum set of source-category attempts; zero-result attempts count as completed coverage, so naturally sparse locations do not block the campaign or cause richer locations to consume their search effort. A bare `Remote` target means fully remote work available in Europe. Explicit conflicts are excluded deterministically, while missing or ambiguous location, remote-policy, or duration evidence remains visible as `needs_review`.

The campaign's free-text `additional_guidance` is included in both vacancy and company research. It is guidance rather than hidden policy: agents use it for interpretation and ranking, while only structured, confirmed constraints drive deterministic exclusion.

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

## Localization

- English and German for Germany (`de-DE`) are application-owned workspace locales; existing workspaces remain English until changed.
- Login and registration use the saved preference or browser language before a workspace exists. Authenticated UI, dates, statuses, errors, and new user-visible agent explanations use the workspace locale.
- Localization uses stable semantic message keys and a central locale registry. Adding a language requires one complete frontend catalog and one agent-language definition, not locale conditionals across product code.
- Agents may reason in English, but visible generated summaries, descriptions, fit explanations, review guidance, onboarding replies, and Master-CV coaching follow the pinned run locale. Stable JSON keys, IDs, codes, flags, and provenance identifiers remain language-neutral.
- User-authored content, historical agent prose, vacancy text, quotations, proper names, and external source material remain in their original language.
- Application language is separate from UI locale: an explicit campaign choice wins, otherwise listed vacancies use their evidenced language and initiative outreach falls back from evidenced recipient language to workspace locale.

## Success Criteria

- A user can inspect what agents did and why.
- Duplicate outreach is blocked by database constraints and deterministic gate logic.
- The backend can explain every send or block decision.
- Agent outputs are structured, source-backed, and schema validated.
- Private, personal, guessed, or weakly sourced contact emails are blocked or routed to review.
- User-descriptive claims in CVs and emails are traceable to approved master CV claim IDs.
- Controlled backend sending preserves the same deterministic safety boundary and remains disabled by default.
