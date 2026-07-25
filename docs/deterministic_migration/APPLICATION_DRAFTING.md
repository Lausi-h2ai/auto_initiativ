# Application Drafting Migration Plan

## Goal

Move factual selection constraints, document structure, rendering, assets, attachments, and packaging into application code while preserving the AI system's ability to write relevant, natural, personalized drafts.

## Preserved Agent Responsibilities

Keep AI responsible for:

- outreach email and cover-letter prose;
- company and vacancy personalization;
- candidate-facing CV wording proposals;
- interpreting ambiguous role requirements;
- explaining genuine evidence gaps;
- selecting among plausible approved claims when exact deterministic matching is insufficient.

Do not replace these responsibilities with templates merely because templates are cheaper or reproducible.

## Structured Application Content Plan

Add `application_content_plan.schema.json`.

Required content:

- schema and plan versions;
- run, campaign, company, contact, and job identifiers as applicable;
- pinned user-profile, master-claim, policy, and Master CV document references;
- application language and recipient type;
- selected claim IDs;
- ordered section and block instructions;
- wording proposals with exact claim references;
- email subject and body;
- cover-letter semantic blocks;
- company/job source references;
- evidence gaps;
- typed review reason codes;
- requested attachment kinds, not arbitrary paths.

The agent cannot provide:

- raw HTML, CSS, JavaScript, image bytes, or file URLs;
- arbitrary attachment paths;
- template or portrait versions different from campaign pins;
- unregistered review severity;
- unsupported user claims.

## Validation

Before rendering, the backend validates:

- all stable IDs in the authenticated workspace;
- campaign-pinned snapshot versions;
- every claim reference exists and is approved for tailoring;
- reviewed claims retain their review state;
- source references resolve to the selected company/job evidence;
- application language follows the campaign or evidenced listing language;
- required document blocks are present;
- attachment kinds are supported;
- no forbidden phrase or claim is present.

Semantic claim-to-text validation remains conservative. A wording proposal that changes factual meaning remains review-required even when it cites a valid claim ID.

## Deterministic Claim Selection

Implement a versioned selector using:

- approved claim categories;
- explicit claim tags;
- normalized role and seniority aliases;
- exact skill and requirement mappings;
- pinned campaign and vacancy fields;
- stable tie-breaking.

The selector outputs ranked claim IDs and feature reasons, not prose.

Applicability requires exact registered mappings and adequate approved-claim coverage. Sparse ledgers, ambiguous requirements, conflicts, and semantic-only matches invoke agent selection.

Run the selector in shadow against existing agent selections before any authority change.

## Application-Owned Rendering

Use the existing structured Master CV renderer and pinned document specification.

The backend owns:

- template and template version;
- design tokens and density;
- portrait asset, crop, and inclusion policy;
- A4 page geometry;
- HTML escaping and asset restrictions;
- section and block identifiers;
- PDF renderer;
- page count, overflow, and fill diagnostics;
- selectable-text checks;
- filenames, paths, hashes, and document records.

Add a semantic business-letter renderer for cover letters. It consumes structured applicant, employer, date, subject, salutation, body, closing, and signature blocks. Country-specific ordering is selected from deterministic destination evidence; ambiguous destination uses the conservative international layout and a review reason.

## Email and Cover-Letter Text

AI-generated text remains authoritative initially.

Provide a deterministic localized fallback for runtime failure only:

- recipient-aware salutation;
- source-backed company or role sentence;
- selected approved claim statements;
- neutral call to action;
- localized closing;
- exact attachment descriptors.

This fallback is labelled for review and does not replace AI based on cost or latency. It can become a normal deterministic option only after separate human paired evaluation shows equal-or-better relevance, tone, and usefulness.

## Shadow and Fallback

### Stage 1: structured plan plus legacy output

Ask the agent for both the structured content plan and existing artifacts. Validate the plan without affecting imported output.

### Stage 2: shadow rendering

Render deterministic HTML/PDF from the content plan beside the legacy agent-authored HTML/PDF. Compare:

- claim coverage;
- visible text;
- sections;
- page count;
- overflow and fill;
- portrait and template preservation;
- PDF text extraction;
- visual review.

### Stage 3: deterministic-first rendering

Use structured rendering when the content plan and renderer both validate. On supported rendering failure, automatically use the retained legacy drafting path and record the fallback.

Safety validation failures do not fall back to unvalidated legacy output.

### Stage 4: deterministic assembly

Generate backend-owned:

- draft and document IDs;
- attachment descriptors;
- filenames and paths;
- content hashes;
- provenance records;
- send intent.

The agent supplies language and evidence references only.

## Comparison Metrics

- successful package completion;
- approved-claim coverage;
- unsupported or unreferenced statements;
- relevance to company/job evidence;
- language correctness;
- tone and readability;
- page count and overflow;
- visual quality;
- portrait/template fidelity;
- attachment availability and hash stability;
- fallback rate.

Critical mismatches:

- invented or unapproved user fact;
- missing required artifact;
- incorrect company, contact, job, language, or pinned snapshot;
- unselectable or image-only PDF;
- template or portrait substitution;
- truncated essential content;
- a previously successful case becoming terminally failed.

## Human Adjudication

Paired reviewers evaluate:

- factual grounding;
- relevance;
- specificity;
- natural language;
- tone;
- visual hierarchy;
- readability;
- completeness.

A deterministic rendering cutover requires no worse result for every corpus case. If a layout class is worse, exclude that class from applicability and retain the legacy agent path.

AI prose or claim-selection replacement requires its own later readiness report; renderer readiness does not authorize replacing creative language work.

## Test Plan

- Content-plan schema and cross-reference validation.
- Unknown, stale, unapproved, and review-blocked claim IDs.
- Initiative and listed-job plans.
- English and German language selection.
- Generic and named recipients.
- Pinned Master CV and neutral fallback.
- All supported templates, portrait policies, sparse/dense content, and one/two-page cases.
- HTML escaping, remote asset rejection, selectable text, overflow, page count, and deterministic hashes.
- Cover-letter destination layouts and ambiguous-country review.
- Legacy fallback on supported renderer/runtime failure.
- Fail closed on safety validation failure.
- Batch drafting, document indexing, download, outbox, and send-intent assembly remain compatible.

## Cutover Criteria

- At least 50 paired packages covering the roadmap categories.
- Every baseline-successful case still produces email, CV, and cover-letter artifacts.
- Zero unsupported claims or pinning errors.
- Human review finds no regression in language, relevance, tone, or visual quality.
- Renderer output is reproducible and passes all document diagnostics.
- Unsupported layouts and ambiguous selection cases automatically use the agent path.
