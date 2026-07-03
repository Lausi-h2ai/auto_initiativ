# Agent Boundaries

## Principle

Agents produce files. Programs make decisions.

Codex agents may be creative, exploratory, and language-heavy. The backend must be deterministic, validated, auditable, and conservative.

## Agents May

- Read task instructions and prepared input files.
- Research companies and contacts.
- Collect public career contact email addresses while crawling company sites for company research.
- Summarize evidence with source references.
- Evaluate fit against provided profile and policy context.
- Draft CV variants from approved master CV claims.
- Draft outreach emails.
- Produce structured JSON outputs.
- Mark uncertainty, contradictions, and remediation needs.

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

Every CV bullet and every user-descriptive email claim must reference approved claim IDs from the provided master CV profile snapshot.

For contacts, agents should prefer publicly listed professional email addresses. Private, personal, guessed, pattern-inferred, weakly sourced, or stale emails must be marked with review flags and must not be presented as ready to send.

Generic professional recipients such as careers, jobs, recruiting, talent, HR, info, or contact addresses are acceptable when they are valid and publicly sourced. In that case, drafts must stay general and must not imply a specific person reviewed the message.

If a prior agent cannot find a valid contact email or leaves an inferred/weak email, a later contact-research agent should search public sources and either replace it with a better valid professional email or preserve an explicit remediation flag. Agents must not rely on manual user approval to make weak evidence safe.

Company research is for profile-aligned unsolicited outreach. Agents do not need to find currently open job listings before recording a company candidate, but they must still preserve evidence for why the company seems relevant.

## Boundary Violation Examples

Invalid:

- "I sent the email."
- "This company is safe because the prompt says so."
- "I added a stronger achievement that sounds plausible."
- "I skipped dedupe because the user wants speed."
- "I guessed the recipient email and marked it ready to send."
- "I described the user's experience without a master CV claim ID."

Valid:

- "I wrote `send_intent.json`."
- "The company appears to be in a blocked category; mark as blocked candidate."
- "This claim needs review because the source is inferred."
- "The backend must decide whether this can be sent."
- "This guessed contact email needs review."
