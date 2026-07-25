# Initial Research: Deterministic Alternatives to Agent Work

## Executive Finding

Auto Initiativ already has the correct outer trust boundary: agents produce untrusted files while the backend owns state, workflow transitions, dedupe, policy, gates, reservations, audit logs, and sending.

The main opportunity is inside the remaining agent workloads. Several agents currently perform two different kinds of work:

1. open-ended discovery, interpretation, coaching, or writing, where AI is useful;
2. extraction, normalization, identification, scoring, ranking, rendering, and packaging, where conventional software can be more reliable.

The recommended boundary is:

```text
AI: discover evidence, resolve ambiguity, propose language
                         |
                         v
Backend: normalize, identify, classify, score, rank, render, gate
```

The migration must not be a broad effort to remove agents. It should replace only bounded responsibilities whose input domain, applicability, output contract, and failure behavior can be proven.

## Current Strengths

The repository already implements substantial deterministic authority:

- versioned, confirmed campaign research plans;
- bounded target fan-out, search attempt accounting, shared budgets, and fan-in;
- code-owned workflow graph definitions and predicates;
- schema validation and normalized persistence;
- company, recipient, and outreach dedupe;
- deterministic vacancy status assignment after evidence import;
- immutable onboarding and Master CV approval;
- application-owned Master CV rendering;
- backend send-intent queueing;
- evaluate-only and transactional reservation gates;
- provider attempt and audit boundaries.

These components should be preserved and used as the architectural pattern for further migration.

## Highest-Risk Finding: Model-Authored Uncertainty Reaches Gates

Agent schemas accept arbitrary `review_flags` strings and agent-assigned confidence values. The gate classifies flags by substring rather than by a closed application-owned type.

Current behavior includes:

- very low confidence being advisory rather than blocking;
- `inferred_pattern` contact emails being advisory;
- unknown email source types being advisory;
- a free-form flag becoming blocking only when its wording contains a recognized hard substring.

Tests explicitly preserve those behaviors. This is unsuitable for a safety boundary because an agent controls both the uncertainty description and the confidence value.

Recommended replacement:

- application-owned reason-code registry;
- backend-owned severity;
- computed evidence quality instead of model confidence;
- deterministic contact eligibility;
- inferred, private, personal, or unobserved addresses structurally ineligible for sending;
- unknown legacy safety flags treated conservatively.

## Fit Scoring and Ranking

Company and vacancy agents create numeric fit scores, decisions, confidence, reasons, and gaps. These values are imported directly.

Vacancy retention uses agent-authored role score, company score, and job confidence. Company retention primarily uses scope status and the company candidate's agent-authored confidence; the required company fit evaluation does not appear to drive that ranking path.

This creates three issues:

- model variance can change candidate priority without input changes;
- the scoring definition cannot be reviewed or reproduced;
- subjective confidence is overloaded as evidence quality and ranking relevance.

Recommended replacement:

- deterministic hard-constraint evaluation;
- explicit feature vector for role, seniority, skills, language, location, work mode, duration, industry, and preferences;
- versioned weights and thresholds;
- missing evidence represented separately from negative evidence;
- source spans for every evidence-derived feature;
- agent fallback for ambiguous taxonomy and semantic mappings.

## Send-Intent Creation

The repository already has a backend `DraftSendIntentQueueService` that assembles an intent from the selected draft, company, contact, attachment references, and approved snapshots, then invokes the gate.

The separate send-intent agent role is therefore redundant. The schema also requires `created_by=codex_agent` even when the backend created the record, which makes provenance inaccurate.

Recommended replacement:

- backend-only send-intent assembly;
- correct producer attribution;
- backward-compatible reading of historical agent-created intents;
- no agent execution for packaging fields that already exist in authoritative state.

## Vacancy Verification

The vacancy verifier is already restricted to supplied URLs, while the backend deterministically assigns vacancy states such as `expired`, `closed`, `apply_unavailable`, `needs_review`, and `verified_open`.

Most of the remaining verifier work is conventional:

- HTTP status and redirect handling;
- canonical URL and application-route extraction;
- JSON-LD `JobPosting` parsing;
- dates, deadlines, and structured employer identity;
- trusted-source classification;
- exact closure signals;
- content hashing and change detection.

An agent is still useful for dynamic, conflicting, or semantically ambiguous pages.

The verifier currently also creates a new fit evaluation. Verification and fit should be decoupled so refreshing source state does not introduce fit-score drift.

## Contact Research

The `contact_research` workflow currently launches the broader company research runtime for one company. It asks that agent to reconstruct a company artifact and find a public address.

A deterministic contact pipeline can cover:

- bounded same-company crawling;
- careers, jobs, contact, about, and imprint pages;
- sitemap and direct navigation links;
- `mailto:` and visible-address extraction;
- common reversible obfuscation;
- syntax and domain normalization;
- exact public observation provenance;
- generic professional alias classification;
- personal/free-mail disqualification.

An agent should remain the fallback for role relevance, named-person interpretation, unusual pages, and unresolved ambiguity.

## Research Discovery and Artifact Construction

The company research agent currently:

- plans queries;
- discovers companies;
- fetches and interprets pages;
- creates stable IDs;
- writes company facts;
- finds contacts;
- evaluates fit;
- assigns confidence;
- writes final domain artifacts.

This is too much responsibility in one probabilistic step.

Recommended pipeline:

```text
deterministic source adapters and agent discovery
    -> raw lead URLs and source observations
    -> backend identity resolution and normalization
    -> deterministic evidence quality and constraints
    -> deterministic fit and ranking where applicable
    -> optional agent summaries and ambiguity resolution
```

Open-world discovery should remain agentic unless a specific source family has a complete deterministic adapter and a proven recall boundary.

## IDs and Evidence Quality

Agents are instructed to create stable IDs, but stable identity should be an application responsibility.

Recommended identities:

- company: normalized registrable domain, with normalized legal-name fallback;
- contact: normalized email plus canonical company identity;
- job: source adapter plus external listing ID, with canonical URL fallback;
- evaluation: entity, profile, policy, and scoring-definition versions;
- observation: normalized URL, field, observation time, and content hash.

Model confidence should be replaced as an authoritative input by explicit evidence dimensions:

- source authority;
- directness;
- freshness;
- corroboration;
- field coverage;
- contradiction state.

The current company enrichment rule takes the maximum incoming confidence, which can make an overconfident observation sticky. Evidence quality should instead be recomputed from current source observations.

## Campaign Constraints

Research-plan compilation is already deterministic, but some hard constraints are inferred from free-text regexes and later matched through location or remote-policy substrings.

The safer deterministic solution is to capture authoritative constraints structurally:

- employment type;
- minimum duration;
- work mode;
- permitted regions;
- commute distance;
- languages and required levels.

Free-text guidance should remain useful for discovery and soft ranking but should never silently become a hard policy.

## Onboarding

The AI recruiter remains valuable for:

- conversation;
- document interpretation;
- contradiction discovery;
- career coaching;
- claim proposal wording.

Conventional software can own:

- IDs and timestamps;
- direct user confirmations;
- typed identity and contact fields;
- work authorization;
- location, availability, and work-mode choices;
- exclusions and limits;
- policy defaults;
- deterministic snapshot merging and provenance.

The correct migration is not to replace the recruiter. It is to add a typed field ledger beside chat and let the backend materialize fields that were directly and structurally confirmed.

## Application Drafting and Rendering

The application drafting agent currently writes tailored CV HTML and cover-letter HTML, then invokes a restricted PDF renderer.

The repository already has a structured, application-owned Master CV renderer. Tailoring should therefore use a schema-valid content plan containing selected claims, ordered blocks, wording proposals, evidence references, language, and review reasons. The backend should own HTML, CSS, assets, portrait policy, page geometry, PDF generation, paths, and hashes.

AI should remain responsible for candidate-facing language, personalization, and ambiguous relevance judgments. Fixed templates may be an availability fallback but should not replace AI prose without paired human evidence of equal or better quality.

## What Should Remain Agentic

The initial research recommends retaining AI for:

- open-ended company and vacancy discovery;
- unfamiliar or JavaScript-heavy public sources;
- ambiguous evidence interpretation;
- natural onboarding conversation and coaching;
- semantic career-claim extraction;
- CV, email, and cover-letter wording;
- company-specific personalization;
- identifying and explaining genuine evidence gaps.

These outputs remain candidates. The application owns their validation, authority, and downstream effects.

## Evaluation Gap

The repository contains strong safety, contract, runtime, workflow, and integration tests, but no equivalent golden evaluation system for:

- onboarding semantic completeness;
- research recall and relevance;
- contact-extraction precision;
- fit-ranking quality;
- paired draft quality.

Before replacing an agent responsibility, the project needs a private replay corpus, paired output comparison, human adjudication where necessary, and a readiness report. The implementation plans in this directory define that system and its cutover criteria.
