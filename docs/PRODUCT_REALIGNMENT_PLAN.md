# Product Realignment Plan

## Product Direction

The app is a local personal AI recruiter, not primarily an internal operations dashboard.

The main user workflow should be:

1. Create or select a user profile.
2. Complete an onboarding chat with a Codex recruiter running in tmux.
3. Validate/import candidate `user_profile.json`, `master_cv_profile.json`, `policy.json`, and `onboarding_review.json` artifacts.
4. Review and approve profile, master CV, and policy snapshots.
5. Create a regional job-search campaign.
6. Launch long-running Codex research in a tmux session/window.
7. Import found companies into the backend.
8. Review company details, fit, risks, sources, and policy conflicts.
9. Later, generate drafts and gated outreach intents.

Developer/operator records remain important, but they should support the workflow rather than lead it.

## Navigation Realignment

Primary product navigation should emphasize:

- Profile.
- Onboarding.
- Campaigns.
- Companies.
- Company detail and review.
- Contacts and fit when they become user-actionable.
- Drafts only after reviewed company/contact context exists.

Secondary Developer Logs navigation should contain:

- Runs.
- Validation results.
- Gate results.
- Audit logs.
- Send intents/send queue.
- Outreach history.
- Raw import diagnostics.

This tick updates the current dashboard navigation to start with onboarding and groups operational pages under Developer Logs. Future ticks should replace the temporary dashboard shell with dedicated product views, without deleting the existing safety/gate infrastructure.

## Backend Source Of Truth

The backend must own:

- Users.
- Profile shells and active profile selection.
- Onboarding sessions.
- Campaigns.
- Agent run records.
- Transcripts and transport logs.
- Imported companies and contacts.
- Review status.
- Profile/master CV/policy snapshot promotion.
- Gate results.
- Reservations and audit logs.

Codex owns only draft work products and structured output files. It does not own state transitions.

## Tmux Runtime Alignment

The tmux bridge is the right runtime for live onboarding and long-running local research because it keeps the user-facing Codex session visible, interruptible, and inspectable.

Do not replace it with a generic `codex exec` batch architecture for chat or campaign research.

Use `codex exec` only where it is a natural fit for a bounded non-interactive file-output task. Even then, stdout/stderr are logs, and backend import remains the authority.

## Safety Constraints

This realignment does not loosen safety rules:

- No Gmail sending.
- No real email adapter sending.
- No autonomous sending.
- No OpenAI API dependency.
- No prompt-only dedupe.
- No bypassing backend gates.
- No deleting safety gate or audit infrastructure.

Outreach remains locked behind deterministic validation, review, reserve-for-send gating, and future explicit unlock work.

## Next Ticks

Recommended sequence:

1. Profile shell and active profile selection.
2. Onboarding chat UI refinement backed by first-class onboarding session records.
3. Campaign creation with region, role, and search constraints.
4. Campaign research tmux run launch and transport log view.
5. Company import, review list, and company detail page.
6. Company accept/reject/needs-review workflow.
7. Contact and fit review views.
8. Later gated outreach draft and send-intent review.

Each tick should keep internal logs accessible but secondary.
