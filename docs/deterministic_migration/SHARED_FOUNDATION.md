# Shared Foundation Plan

## Goal

Provide one application-owned mechanism for introducing, comparing, proving, cutting over, and rolling back deterministic alternatives without reducing onboarding, research, or drafting capability.

## Capability Registry

Create a trusted code-owned registry. Each capability definition contains:

- stable capability ID;
- deterministic implementation key and version;
- agent implementation key;
- supported input and output contract identifiers;
- mode: `agent_authoritative`, `shadow`, or `deterministic_first`;
- applicability predicate key;
- deterministic timeout;
- fallback reason-code set;
- comparison strategy key;
- readiness policy key.

Initial capability IDs:

- `onboarding_field_materialization`;
- `job_source_extraction`;
- `job_verification`;
- `contact_extraction`;
- `company_fit_scoring`;
- `job_fit_scoring`;
- `application_claim_selection`;
- `application_document_rendering`;
- `send_intent_assembly`.

Definitions are versioned application code. Active work records the version used. Deploying a new version does not silently reinterpret historical comparisons.

## Runtime Selection

Add one internal facade:

```text
execute_capability(capability_id, context, input_ref) -> CapabilityExecutionResult
```

Behavior:

- `agent_authoritative`: invoke the existing agent implementation only.
- `shadow`: invoke the agent authoritatively and the deterministic implementation independently. Persist both output references and a comparison. Import or materialize only the agent result.
- `deterministic_first`: evaluate the deterministic applicability predicate. If applicable, execute and validate the deterministic result. On unsupported input, ambiguity, validation failure, bounded timeout, or declared recoverable error, invoke the agent fallback. Persist the selection and reason.

Deterministic output conflicts, internal corruption, workspace mismatch, or safety invariant failures are not recoverable by trusting an agent result. They fail closed and create a review issue.

The facade must be idempotent through a workspace-scoped execution key derived from capability, version, logical entity, immutable input hash, and generation.

## Persistence

Add an additive `CapabilityComparison` record containing:

- comparison ID and workspace;
- capability ID and version;
- input hash and immutable input references;
- agent output references and hashes;
- deterministic output references and hashes;
- normalized comparison JSON;
- critical mismatch codes;
- metrics JSON;
- adjudication status and reviewer;
- final verdict;
- timestamps.

Use `AuditLog` for execution events:

- capability selected;
- deterministic path applicable or unsupported;
- deterministic completed or failed;
- fallback invoked;
- comparison completed;
- readiness verdict generated;
- cutover mode changed.

Do not create a second workflow-state store. Domain rows and existing workflow records remain authoritative.

## Schemas and Types

Add code-consumed schemas for:

### `source_observation.schema.json`

Required fields:

- schema and observation versions;
- stable observation ID;
- entity kind and external entity ID;
- normalized source URL;
- observed timestamp;
- HTTP/content metadata where applicable;
- content hash;
- field key and normalized value;
- exact evidence span or structured-data pointer;
- extraction method and implementation version;
- source authority;
- directness;
- contradiction state;
- review reason codes.

### `capability_comparison.schema.json`

Required fields:

- capability and implementation versions;
- input hash;
- normalized agent and deterministic summaries;
- field-level match results;
- critical mismatches;
- quantitative metrics;
- adjudication status;
- readiness contribution.

### Typed review reasons

Replace arbitrary safety-relevant flags with a code-owned registry containing:

- stable code;
- entity and field applicability;
- severity;
- user-visible localization key;
- whether the reason blocks approval, ranking, verification, or sending;
- remediation action.

Unknown legacy flags are preserved for display but mapped conservatively at authority boundaries.

## Evidence Quality

Create a pure, versioned evidence-quality calculator. Inputs:

- source authority;
- whether the value is directly observed;
- observation age;
- number of independent corroborating sources;
- required-field coverage;
- contradiction state.

Outputs:

- component values;
- a display grade;
- review reasons;
- whether the evidence is sufficient for a particular deterministic decision.

Agent confidence is never an input. Existing confidence fields remain readable during migration and may remain visible in historical UI.

## Contact and Gate Hardening

Implement a deterministic contact-eligibility service before changing sending behavior.

An eligible address requires:

- exact normalized email observed on an allowed public source;
- source URL, observation timestamp, and content hash;
- professional context;
- acceptable domain relationship or explicitly allowed public recruiting provider;
- no private, personal, guessed, inferred-pattern, or unresolved evidence reason.

DNS and MX checks can disqualify an impossible domain but cannot establish ownership or public provenance.

Update evaluate-only and reserve-for-send to consume typed reasons and deterministic eligibility. Low agent confidence and arbitrary flag wording no longer affect safety authority. Inferred-pattern and unobserved addresses block.

Keep this gate work separate from research cutover so stricter safety cannot accidentally authorize a deterministic research implementation.

## Send-Intent Assembly

Make the existing backend queue service the sole normal creator of new send intents.

- Add `backend` as a valid producer.
- Preserve reading of historical `codex_agent` intents.
- Generate IDs, snapshot references, attachments, paths, existence markers, and hashes from authoritative state.
- Remove new workflow dependencies on the send-intent agent after compatibility tests pass.
- Do not change provider or sending enablement.

## Private Evaluation Corpus

Store the corpus under:

```text
artifacts/deterministic-eval/
  manifest.json
  onboarding/
  research/
  contacts/
  fit/
  drafting/
  adjudications/
  reports/
```

The directory must be ignored by Git. It may contain unsanitized local historical runs, but:

- it remains local and workspace-scoped;
- commands never print raw personal content into general logs;
- the manifest stores hashes, capability categories, locale, and consent/provenance, not copied secrets;
- replay disables email delivery and application submission;
- public web pages are frozen as local snapshots for repeatability.

## Comparison and Readiness

Implement normalizers per capability so semantically irrelevant formatting differences do not create false mismatches.

Readiness evaluation requires:

- minimum corpus coverage from the roadmap;
- 100% schema and contract validity;
- 100% replay idempotency;
- zero critical safety or factual mismatches;
- equal-or-better completion;
- capability-specific quality metrics;
- completed human adjudication for semantic output;
- no unresolved comparison records.

Generate both JSON and Markdown readiness reports. A report may return:

- `insufficient_evidence`;
- `mismatches_present`;
- `ready`.

Like workflow graph shadow readiness, `ready` permits a separate cutover tick but does not perform cutover.

## Test Plan

- Registry rejects unknown implementations, modes, predicates, and comparison strategies.
- Execution keys are stable and workspace-isolated.
- Shadow mode never imports deterministic output.
- Deterministic-first invokes fallback for every registered recoverable reason.
- Safety invariant failures never fall back to agent authority.
- Replays are byte-stable after normalization.
- Historical records without new provenance remain readable.
- Typed review reasons localize correctly and unknown legacy flags fail conservatively.
- Contact eligibility blocks inferred, private, personal, stale, missing-source, and contradictory evidence.
- Send-intent creation is deterministic and idempotent.
- The corpus cannot be committed accidentally.
- Readiness verdicts are stable and fail closed when evidence is incomplete.

## Acceptance Criteria

- All capabilities can remain `agent_authoritative` with no behavior change.
- Shadow computation cannot mutate authoritative domain rows.
- Every deterministic-first fallback is visible and auditable.
- Existing onboarding, research, drafting, and sending interfaces continue to work.
- A single capability can be enabled, disabled, or rolled back without changing another capability.
