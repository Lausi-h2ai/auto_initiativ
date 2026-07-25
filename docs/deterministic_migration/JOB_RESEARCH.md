# Job Research Migration Plan

## Goal

Move bounded source parsing, identity, verification, contact extraction, fit scoring, and ranking into versioned application code without reducing relevant-job discovery or candidate breadth.

Open-world search, unfamiliar sources, ambiguous evidence, and natural-language guidance interpretation remain agentic.

## Preserved Capabilities

- confirmed multi-target research plans;
- target-aware search coverage;
- general web, portal/directory, and employer/regional search categories;
- dynamic discovery of employer pages;
- listed-job and initiative-outreach separation;
- company and job candidate creation;
- public contact discovery;
- source-backed fit explanations;
- unknown evidence retained as reviewable;
- deterministic target scope, budgets, fan-in, retention, and downstream preparation.

Deterministic discovery is additive until a specific source surface proves equal-or-better recall.

## Source Observation Pipeline

Implement:

```text
lead URL
  -> bounded fetch or browser snapshot
  -> source adapter
  -> SourceObservation records
  -> canonical identity and normalized domain entities
  -> verification, constraints, fit, and ranking
```

Adapters never write domain rows directly and never assign final eligibility or workflow transitions.

## Adapter Registry

Create a code-owned adapter registry with:

- stable adapter ID and version;
- source signature predicate;
- permitted URL/domain behavior;
- fetch requirements;
- extraction fields;
- completeness predicate;
- ambiguity and fallback reason codes.

Implement the generic adapters first:

- JSON-LD `JobPosting`;
- schema.org `Organization`;
- canonical, OpenGraph, and standard metadata;
- sitemap and same-employer career-link enumeration;
- plain HTML application-link and closure-signal extraction.

Select ATS-specific adapters mechanically from the locked corpus:

1. identify platform signatures and source families;
2. order by number of real pages covered;
3. implement only adapters with enough corpus evidence to evaluate;
4. keep all other sources agent-authoritative.

This avoids guessing which integrations matter.

## Discovery Strategy

During shadow mode:

- deterministic adapters process every compatible lead the agent discovers;
- deterministic source enumeration may add leads;
- no deterministic result suppresses an agent result;
- the union is measured against human-adjudicated relevant candidates.

In deterministic-first mode for a proven source family:

- the adapter owns extraction for recognized compatible pages;
- the agent receives normalized observations rather than re-extracting the page;
- the agent continues searching other source categories;
- if the adapter yields fewer candidates than expected, encounters ambiguity, or cannot meet required fields, the agent automatically follows up.

Campaign target, effort, search categories, budget, and coverage remain backend-owned.

## Canonical Identity

Generate identities in the backend:

- company identity from normalized registrable domain, with normalized legal-name and country fallback;
- job identity from adapter ID and external listing ID, with normalized canonical URL fallback;
- contact identity from canonical company identity and normalized email;
- evaluation identity from entity, profile snapshot, policy snapshot, and scoring-definition versions.

Aliases are stored explicitly. Agent-provided IDs become import references, not canonical identity authority.

## Deterministic Vacancy Verification

The verifier consumes the supplied vacancy and frozen current observations.

It may establish:

- page accessibility and HTTP status;
- redirect outcome;
- employer identity match;
- canonical listing and application URL;
- application-route availability;
- date posted and valid-through deadline;
- direct closed, expired, or filled signal;
- trusted source classification;
- observation timestamp and content hash.

It may assign `verified_open` only when the existing application-owned verification policy has sufficient direct evidence. Otherwise:

- explicit closed/expired evidence produces the deterministic terminal state;
- missing or contradictory evidence produces `needs_review`;
- unsupported or ambiguous pages invoke the restricted existing verifier agent.

Verification never writes a new fit evaluation. Fit recomputes only when normalized vacancy content or its pinned profile, policy, or scoring version changes.

## Deterministic Contact Extraction

Implement a bounded crawler restricted to the canonical company:

- homepage;
- careers and jobs pages;
- contact and about pages;
- imprint/legal page;
- same-domain sitemap;
- directly linked recruiting pages.

Extract:

- `mailto:` addresses;
- visible email strings;
- supported reversible obfuscation;
- nearby name, title, heading, and short evidence span;
- source URL and page hash.

Eligibility ranking:

1. company-published recruiting/careers address;
2. company-published HR/talent address;
3. named recruiting professional with direct public evidence;
4. generic public company address;
5. unobserved, inferred, private, or personal address: ineligible.

DNS is a disqualifier only. It is not provenance. If no eligible address is found or professional relevance is ambiguous, invoke the agent contact-research path.

## Fit Feature Model

Create separate deterministic scoring definitions for company and vacancy fit.

Hard constraints:

- explicit company/domain/industry/keyword/role exclusion;
- work authorization when a published requirement conflicts;
- employment type;
- minimum duration;
- work mode and remote region;
- geographic target;
- required language where structured evidence exists.

Soft features:

- normalized target role and seniority;
- approved skill and claim tags;
- responsibility overlap;
- industry and company-type preference;
- location preference;
- evidence freshness and coverage.

Rules:

- explicit hard conflict determines `blocked_by_policy`;
- missing required evidence determines `needs_review`;
- unknown evidence is not scored as a negative;
- remaining features produce a versioned weighted score;
- thresholds map scores to `promising` or `weak_fit`;
- every feature records source or approved-claim references.

Agent fallback handles semantic mappings that cannot be established through exact taxonomy, registered aliases, or structured evidence.

## Ranking

Rank only after deterministic scope and policy checks.

Vacancy ordering:

1. exact scope match before review-needed;
2. verified open before unverified;
3. deterministic role fit;
4. deterministic company fit;
5. freshness;
6. deterministic evidence quality;
7. stable job identity.

Company ordering:

1. exact scope match before review-needed;
2. deterministic company fit;
3. deterministic evidence quality;
4. normalized name and stable identity.

Do not use agent confidence as an authoritative ranking input.

## Comparison Metrics

Discovery:

- relevant candidate recall;
- human-labelled must-retain recall;
- relevant yield by source category;
- target and source-family coverage;
- duplicate rate.

Extraction and verification:

- field precision and recall;
- canonical identity stability;
- open/closed/expired status agreement;
- false `verified_open` count;
- fallback rate and reason distribution.

Fit and ranking:

- hard-constraint agreement;
- must-retain recall;
- top-k relevance and ordering;
- missing-evidence handling;
- cross-run stability.

## Test Plan

- Adapter signature, completeness, and fallback contract tests.
- Frozen JSON-LD, ATS, HTML, redirect, closed, expired, missing-date, inaccessible, and contradictory fixtures.
- No cross-domain or unbounded crawler navigation.
- Canonical identity and alias replay.
- Contact extraction, obfuscation, personal email, generic alias, no-contact, DNS failure, and source-provenance cases.
- Fit transition tables for every hard constraint and unknown state.
- Stable score and ranking snapshots.
- Agent fallback for unknown source, ambiguous employer, dynamic failure, sparse evidence, and semantic mapping.
- Target isolation, search attempts, shared budgets, barrier, workspace isolation, and graph shadow tests remain green.
- End-to-end listed-job research still produces retained jobs and manual-submit application preparation.

## Cutover Criteria

- Corpus requirements from the roadmap are met.
- Zero false `verified_open` results.
- Zero inferred/private contacts classified eligible.
- Every human-labelled must-retain candidate remains retained.
- Relevant candidate recall and total retained breadth are no lower than the agent baseline.
- Unknown source families and ambiguous semantic cases automatically use the agent path.
- A source adapter, verifier, contact extractor, fit scorer, and ranking definition receive independent readiness verdicts and cutover ticks.
