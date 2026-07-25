# Deterministic Capability Migration Roadmap

## Purpose

Auto Initiativ should move work from AI agents to conventional software only when the replacement is demonstrably as capable or better. The protected product capabilities are:

- onboarding a user into usable, reviewable profile snapshots;
- discovering and retaining relevant jobs;
- producing grounded, useful application drafts and documents.

This program is deliberately conservative. It does not treat lower cost, lower latency, or easier testing as sufficient justification for a replacement. An AI implementation remains available whenever a deterministic implementation is unsupported, ambiguous, or has not passed a strict non-inferiority gate.

The initial analysis behind this roadmap is recorded in [INITIAL_RESEARCH.md](INITIAL_RESEARCH.md).

## Program Decisions

### Execution modes

Every replaceable capability has one code-owned mode:

1. `agent_authoritative`: current agent behavior remains authoritative.
2. `shadow`: deterministic and agent implementations run from equivalent inputs, but only the agent result can affect product state.
3. `deterministic_first`: deterministic output is authoritative only inside its proven applicability boundary. Unsupported, ambiguous, or failed inputs automatically use the existing agent implementation.

There is no `deterministic_only` mode in this program. AI fallback is retained permanently for non-privileged work. Safety, policy, workflow authority, approvals, and side effects are always deterministic and never fall back to AI.

### Strict non-inferiority

A deterministic path may become authoritative only when:

- it has zero critical errors in the locked evaluation corpus;
- its combined deterministic-first plus fallback completion rate is no worse than the agent baseline;
- it does not reduce required-field completeness, relevant-job recall, document availability, or factual grounding;
- human paired review finds its user-facing results equal or better where semantic quality matters;
- identical inputs produce identical normalized outputs, IDs, reason codes, and hashes;
- a readiness report returns `ready`;
- cutover is performed in a separate, explicit implementation tick.

When a deterministic implementation performs worse for a class of inputs, narrow its applicability boundary. Do not accept the regression as an aggregate tradeoff.

### Automatic fallback

Fallback is automatic for onboarding, research, verification, contact discovery, fit evidence interpretation, and drafting. Every fallback records a stable reason code, input hash, deterministic version, and output reference.

Fallback must not:

- bypass schema validation or import boundaries;
- turn uncertain evidence into an authoritative fact;
- retry an irreversible or uncertain provider action;
- broaden a confirmed campaign target or budget;
- weaken review, approval, or sending gates.

## Workstreams

### 1. Shared foundation

Implement the common capability registry, execution modes, provenance records, typed review reasons, evidence-quality model, local evaluation corpus, paired comparison runner, and readiness reporting described in [SHARED_FOUNDATION.md](SHARED_FOUNDATION.md).

This work is additive and must not change user-visible workflow behavior while all capabilities remain `agent_authoritative`.

### 2. Onboarding

Keep the AI recruiter and semantic career-claim extraction. Move directly confirmed, structurally representable profile and policy fields into an application-owned field ledger and deterministic snapshot materializer. See [ONBOARDING.md](ONBOARDING.md).

Cutover is field-family specific. Chat-only onboarding remains supported and automatically uses the agent path for unstructured or uncovered information.

### 3. Job research

Keep open-world discovery and ambiguous source interpretation agentic. Add deterministic source adapters, source observations, canonical identities, vacancy verification, contact extraction, and fit scoring where the evidence contract is explicit and testable. See [JOB_RESEARCH.md](JOB_RESEARCH.md).

Job discovery must initially be additive: deterministic leads cannot suppress agent leads until the relevant source family passes its own readiness gate.

### 4. Application drafting

Keep candidate-facing language generation and ambiguous relevance judgments agentic. Replace agent-authored HTML, layout, attachment assembly, and send-intent packaging with validated structured content plans and application-owned rendering. See [APPLICATION_DRAFTING.md](APPLICATION_DRAFTING.md).

The legacy drafting path remains available as an audited fallback until structured rendering has passed every required document case.

## Delivery Sequence

Each numbered item is a separate meaningful tick and commit unless a smaller split is required by risk.

1. Commit these planning and research documents.
2. Add the capability registry, modes, audit contract, comparison persistence, and evaluation harness without changing authority.
3. Lock the private evaluation corpus and record baseline agent results.
4. Replace arbitrary safety-relevant review flags with typed application-owned reasons.
5. Make contact eligibility and send-intent provenance deterministic.
6. Add onboarding field events and shadow snapshot materialization.
7. Add source observations and generic job extraction in shadow mode.
8. Add deterministic vacancy verification in shadow mode.
9. Add deterministic contact extraction in shadow mode.
10. Add deterministic fit scoring and ranking in shadow mode.
11. Add the structured application content plan and shadow document rendering.
12. Generate readiness reports independently for each capability.
13. Cut over only capabilities with a `ready` verdict, one explicit tick at a time.

## Compatibility and Rollback

- Existing public onboarding, campaign, research, verification, drafting, and download endpoints remain compatible.
- New structured onboarding input is additive; existing chat payloads remain valid.
- Existing agent JSON schemas remain readable during migration.
- Database changes are additive. Historical records retain their original producer and schema attribution.
- Active campaign and workflow graph runs remain pinned to their existing definitions.
- A capability can be rolled back to `agent_authoritative` without rewriting historical domain rows.
- The local evaluation corpus is never committed and never becomes application state.

## Completion Criteria

The program is complete when:

- every capability has an explicit owner, implementation version, applicability contract, and fallback policy;
- no safety-relevant decision depends on model-authored confidence or free-form flag wording;
- deterministic source adapters and verifiers cover only proven source families;
- onboarding still produces promotable user profile, master CV claim, and policy snapshots;
- job campaigns find and retain at least the same relevant candidates as the agent baseline;
- every successful drafting scenario still produces grounded email, CV, and cover-letter artifacts;
- every deterministic cutover is supported by replayable evidence and an explicit readiness report;
- AI remains available for open-world, ambiguous, conversational, and creative work.
