# Agent Boundaries

## Principle

Agents produce files. Programs make decisions.

Codex agents may be creative, exploratory, and language-heavy. The backend must be deterministic, validated, auditable, and conservative.

## Agents May

- Read task instructions and prepared input files.
- Research companies and contacts.
- Summarize evidence with source references.
- Evaluate fit against provided profile and policy context.
- Draft CV variants from approved master CV claims.
- Draft outreach emails.
- Produce structured JSON outputs.
- Mark uncertainty, contradictions, and review needs.

## Agents Must Not

- Send email.
- Call Gmail or any email-sending adapter.
- Modify database state directly.
- Decide that safety gates pass.
- Override dedupe rules.
- Invent career facts.
- Hide unsupported claims in prose.
- Treat prompt instructions as policy if they conflict with stored `policy.json`.

## Backend Responsibilities

- Prepare run folders.
- Provide scoped input context.
- Validate every output.
- Persist accepted records.
- Enforce dedupe in the database.
- Evaluate safety gates.
- Reserve sends transactionally.
- Write audit logs.
- Call email adapters only after gates pass.

## Required Agent Output Behavior

When an output may be consumed by code, the agent must write JSON matching a schema in `schemas/`.

When evidence is weak, the agent must:

- Use lower confidence.
- Add review flags.
- Preserve source references.
- Avoid unsupported personalization.
- Avoid unsupported CV claims.

## Boundary Violation Examples

Invalid:

- "I sent the email."
- "This company is safe because the prompt says so."
- "I added a stronger achievement that sounds plausible."
- "I skipped dedupe because the user wants speed."

Valid:

- "I wrote `send_intent.json`."
- "The company appears to be in a blocked category; mark as blocked candidate."
- "This claim needs review because the source is inferred."
- "The backend must decide whether this can be sent."

