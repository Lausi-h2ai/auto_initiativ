# Master CV Builder

Status: governing feature contract. The backend lifecycle, deterministic rendering, portrait handling, agent runtime, approval, export, campaign pinning, and core workspace UI are implemented. Remaining completion work includes UI version comparison/restore, explicit first-visit routes, template filters, duplicate/archive controls, and dedicated desktop/mobile browser journeys. A requirement in this document is not evidence that the corresponding UI is complete.

## 1. Product decision

Create a dedicated **Master CV** item in the left navigation immediately after **My story**:

1. Mission control
2. Companies
3. My story
4. Master CV
5. Documents
6. Open positions
7. Needs me

Master CV design is not another mandatory onboarding stage. Onboarding remains responsible for gathering and approving career facts, preferences, policy, source documents, and an optional portrait. After approval, it leads naturally into the separate Master CV workspace.

This separation is required because onboarding is a one-time foundation, while Master CV creation is creative and iterative. Users must be able to revisit templates, portrait crops, wording, and version comparisons without reopening onboarding. An approved profile and approved Master CV remain usable while a revised Master CV is still a candidate.

Master CV creation is strongly recommended, but it is not a campaign blocker. Until a Master CV document is approved, tailored CV generation uses the repository-owned neutral fallback.

## 2. End-to-end user journey

### During onboarding

The recruiter conversation continues to collect approved career facts and explains that:

- an uploaded CV can seed the Master CV;
- a portrait can be uploaded now or later; and
- design work happens after the factual profile is approved.

Career documents and portraits uploaded during onboarding become durable, workspace-scoped assets. They must not remain accessible only inside an onboarding run directory.

### After onboarding approval

The success state says:

> Your career foundation is approved. Now turn it into a Master CV your application team can reuse.

It offers **Build my Master CV**, **View approved profile**, and **Continue later**. Mission Control shows the readiness sequence:

```text
✓ Career story approved
○ Master CV ready
○ Campaign active
```

### First Master CV visit

The user chooses, or the agent recommends, one of four entry routes:

1. Improve my uploaded CV.
2. Build from my approved profile.
3. Import LinkedIn PDF or pasted profile text.
4. Revise my existing Master CV.

The agent begins with a concise diagnostic rather than a generic questionnaire. It identifies supported content, weak or missing bullets, unconfirmed metrics, section-order recommendations, page-length pressure, and suitable template and portrait placements. It then asks one focused question at a time.

### Iteration and approval

The user can chat with the agent; switch templates; change colors, density, typography, section order, and page goal; manage the portrait; edit preview text; compare the candidate with the approved version; and review unsupported or proposed facts.

Every meaningful change creates or updates a candidate snapshot and produces a new preview. No candidate replaces the approved Master CV until the user explicitly approves it. Approval is a deterministic backend operation, never an agent action.

## 3. Master CV workspace

### Responsive layout

Desktop uses three coordinated panes:

```text
┌──────────────────────────────────────────────────────────────────┐
│ Master CV      Draft · 6 changes       Export   Approve version  │
├──────────────────┬────────────────────────────┬──────────────────┤
│ CV adviser       │ Live A4 preview            │ Design           │
│ conversation     │ Page 1 / Page 2            │ Content          │
│                  │                            │ Claims           │
│ Upload controls  │                            │ Portrait         │
│ Suggested reply  │                            │ Versions         │
├──────────────────┴────────────────────────────┴──────────────────┤
│ Saved just now · 2 items need review · Based on profile v4       │
└──────────────────────────────────────────────────────────────────┘
```

The target proportions are 30% conversation, 45% preview, and 25% inspector. On narrower screens the inspector becomes a drawer. On mobile the workspace switches between **Chat**, **Preview**, and **Edit** tabs instead of compressing all three panes.

### Header

The header contains:

- title and current language/market;
- status: `not_started`, `candidate`, `needs_review`, or `approved`;
- last-saved time;
- HTML and PDF export;
- explicit **Approve version** action; and
- duplicate, archive, and restore-version actions in an overflow menu.

### Agent conversation

The conversation pane contains a persistent transcript, CV/document upload, LinkedIn PDF or pasted-text import, portrait upload, suggested replies, extraction/rendering activity states, and the compact list of source files used. The agent explains visible editorial decisions, such as why it reordered sections.

### Live preview

The preview is the visual focus and provides:

- real A4 proportions, page shadows, and a neutral surrounding background;
- page count, page-break, and overflow indicators;
- zoom controls;
- print-preview and editable modes;
- selectable document text;
- sections linked to inspector controls;
- highlighting for text that needs review; and
- immediate template, design-token, and portrait updates.

### Inspector

The inspector has five tabs:

- **Design:** template, accent, typography, density, spacing, and one/two-page goal.
- **Content:** section order, headings, visibility, and structured block editing.
- **Claims:** claim references, unresolved facts, and proposed claims.
- **Portrait:** upload, crop, zoom, focal point, placement, and inclusion policy.
- **Versions:** approved and candidate history, restore, and compare.

### Template gallery

The initial gallery contains all thirteen upstream templates. Each entry shows a full thumbnail, name, intended use, ATS/readability label, density, portrait placement, supported page counts, suitable markets and role families, and **Preview with my content**.

Filters include ATS-friendly, portrait prominent, portrait subtle, single column, two column, compact, editorial, German/Swiss, one page, and two pages.

The surrounding application retains Auto Initiativ's forest-and-paper visual language. Templates retain their own upstream aesthetics inside the preview.

## 4. Authority and trust boundaries

- `master_cv_profile.json` is the only source for personal career claims used in CV content. The approved user-profile snapshot may supply approved identity, contact, locale, market, and preference fields, with explicit field references. Source documents are evidence and extraction inputs; they cannot bypass claim approval.
- The builder may select, omit, reorder, or shorten approved material. It may propose corrections or missing facts, but it may not silently add them to an approved claim ledger or approved document.
- Code-consumed agent output is JSON validated against an application-owned schema. It contains stable IDs, provenance, source references, confidence where relevant, and review flags.
- The agent cannot write database state, approve claims or documents, select arbitrary image bytes, access unrestricted paths, or emit executable HTML, JavaScript, or CSS.
- The application owns authentication, workspace isolation, database state, templates and their allowed settings, rendering, asset processing, immutable approval, audit events, and downstream pinning.
- The user or agent may choose among allowed templates and design options; the backend validates that choice against the pinned catalog and renders it deterministically.
- Unsupported factual text is `needs_review` and blocks approval. Wording-only edits retain claim references only when deterministic checks establish that factual meaning did not change; otherwise they also require review.
- Approved versions are immutable. Preview HTML is derived output, never the source of truth.
- Every tailored output records the exact approved profile, claim ledger, Master CV document, template, and portrait revisions that produced it.

## 5. Upstream asset integration

Vendor the complete MIT-licensed `yanliudesign/resume-builder-skill` repository at a pinned commit:

```text
third_party/yanliudesign-resume-builder-skill/
  SKILL.md
  schema/
  prompts/
  guides/
  templates/
  LICENSE
```

Keep the vendored files unchanged so provenance remains clear. Record the upstream repository URL, pinned commit, license, vendoring date, and update procedure in `third_party/yanliudesign-resume-builder-skill.UPSTREAM.md`.

Application adaptations belong separately under the target structure:

```text
backend/assets/master_cv/
  prompts/
  templates/
  template_catalog.json
  THIRD_PARTY_NOTICES.md
```

Existing application-owned adapters may migrate into this structure incrementally. They must not overwrite the vendored source.

| Upstream asset | Auto Initiativ use |
| --- | --- |
| `SKILL.md` | Interview, diagnosis, template-selection, and rendering workflow |
| `prompts/beautify.md` | Uploaded-CV improvement route |
| `prompts/interview.md` | Build-from-profile conversational route |
| `prompts/linkedin-import.md` | LinkedIn PDF and pasted-text route |
| `prompts/editable-version.md` | Persistent editable-preview interaction |
| `schema/resume-data.md` | Input to the application-owned document schema design |
| Writing guide | Agent reference for bullet diagnosis and rewriting |
| All thirteen templates | Initial template catalog |

Preserve the upstream license and attribution in distributions containing the adapted assets.

## 6. Template normalization

The initial catalog contains Atelier, Classic ATS, Editorial Banner, Elegant Serif, Executive, Ledger, Modern Sidebar, Photo Corporate, Photo Minimal, Pillar, Swiss, Tech Compact, and Timeline. A template ships only after deterministic normalization and QA.

For every template:

- preserve the original layout and CSS where compatible with the trust boundary;
- convert Letter dimensions and print rules to A4;
- remove sample names, employers, contact details, metrics, and achievements;
- replace sample content with stable slots and block IDs;
- add optional portrait placement;
- support one- and two-page output where practical;
- keep meaningful text selectable;
- omit or conditionally render empty sections;
- validate page count, page breaks, and overflow;
- provide German, Swiss, and English section labels;
- omit skill ratings unless an approved claim supports the level; and
- omit references unless explicitly supplied and approved.

Template metadata follows a versioned application schema and includes at least:

```json
{
  "template_id": "photo-corporate",
  "template_version": "1.0",
  "name": "Photo Corporate",
  "layout": "sidebar",
  "ats_profile": "moderate",
  "density": "medium",
  "supports_portrait": true,
  "portrait_placement": "banner_overlap",
  "supported_pages": [1, 2],
  "supported_markets": ["de-DE", "de-CH", "en-CH", "international"]
}
```

QA must verify sanitized content, A4 geometry, selectable text, supported locales, optional portrait behavior, deterministic rendering, and overflow/page-count behavior with representative sparse and dense documents.

## 7. Portrait UX and processing

Portrait support is available across the catalog from the first release. Photo Corporate and Photo Minimal provide prominent layouts; other templates use subtler header or sidebar variants.

The portrait editor supports upload, zoom, pan, focal point, circle/rounded/rectangular previews, cross-template crop comparison, replacement, and removal. Inclusion policy is one of **Always include**, **German/Swiss CVs**, or **Never include**. For German and Swiss markets, inclusion defaults to enabled when an active portrait exists, but the user remains in control.

The backend:

- accepts JPEG, PNG, and WebP, plus HEIC only when the local decoder supports it;
- verifies decoded format instead of trusting the extension or claimed MIME type;
- applies EXIF orientation, strips EXIF and location metadata, and converts to sRGB;
- enforces byte-size, pixel-dimension, and resolution limits before expensive processing;
- creates immutable normalized variants and stores crop/focal metadata separately;
- stores assets locally, application-owned, and workspace-scoped with content hashes and version history; and
- gives renderers only the selected backend-produced variant, normally through a bounded data URI.

File URLs, network URLs, arbitrary data URIs, cross-workspace asset references, agent-selected images, and unrestricted file paths are forbidden. The model does not receive portrait bytes or analyze the user's appearance. Cropping is user-controlled and rendering is backend-controlled.

## 8. Persistent direct editing

Rendered elements carry stable identifiers and factual references:

```html
<p
  contenteditable="true"
  data-block-id="experience-company-1-bullet-2"
  data-claim-refs="claim-17 claim-22"
></p>
```

The example describes renderer output; the agent cannot author arbitrary HTML.

Saving an edit:

1. sends a structured block patch to the backend;
2. creates or updates a candidate Master CV snapshot;
3. preserves claim references only for verified wording-only edits;
4. flags potentially factual changes for review;
5. re-renders from validated structured data; and
6. never mutates approved HTML or an approved snapshot.

Conversation edits and direct edits operate on the same candidate state, use optimistic concurrency or an equivalent conflict check, and produce audit events for material changes.

## 9. Application data model and schemas

Keep three separate layers:

| Layer | Purpose |
| --- | --- |
| `MasterCvProfileSnapshot` | Immutable approved claim ledger and factual provenance |
| `MasterCvDocumentSnapshot` | Content selection, wording, layout, design, and exact references |
| `Document` | Uploaded career documents and generated HTML/PDF files |

### MasterCvDocumentSnapshot

Stores a stable document snapshot ID; workspace; exact approved user-profile and master-claim snapshot foreign keys; parent snapshot; version; template ID and version; locale and market; page goal; design tokens; ordered sections and blocks; claim and profile-field references; portrait asset and variant reference; review flags; candidate/approved/superseded/rejected status; validated raw JSON; content hash; and timestamps.

### MasterCvBuilderSession

Stores stable session and run IDs, workspace, selected entry route, current base document snapshot, current candidate snapshot, status, transcript, candidate state, and started/completed timestamps.

### ProfileAsset

Stores stable asset ID, workspace, type, original and normalized application-owned paths, MIME type, dimensions, content hash, status, active version, immutable variant history, and processing metadata. Database records never grant the agent raw path access.

### Master CV claim proposals

`master_cv_claim_proposals.json` may propose missing facts but cannot add them to an approved CV. Every proposal has a stable ID, proposed statement, category, source references, confidence where available, review reason, `needs_review: true`, and a suggested relationship to existing claims. Approval routes through the existing claim workflow and creates a new immutable claim-ledger snapshot.

### Schema evolution

The current `schemas/master_cv_document.schema.json` and `schemas/master_cv_claim_proposals.schema.json` are initial `1.0` contracts. Before feature completion they must be versioned or extended to cover the target fields above, including snapshot identity, template version, market, page goal, design tokens, profile-field references, portrait variant, review flags, lifecycle status, source confidence, and content hash. Migration must retain validation for existing stored snapshots and preserve reproducibility.

All foreign-key lookups and uniqueness constraints are workspace-scoped. Approval transitions and supersession happen transactionally and create audit records.

## 10. Agent integration

Use one focused `master_cv_builder` specialist through the existing restricted Pi RPC architecture. This matches OpenAI's recommendation to begin with the smallest agent that owns one clear task and to package specialist instructions, tools, guardrails, and structured output together.

Prompt priority is:

1. Auto Initiativ safety, authority, and approved-claim rules.
2. Structured-output schema and tool contract.
3. Adapted upstream `SKILL.md` workflow.
4. The relevant upstream route prompt.
5. Dynamic approved user profile, approved claim ledger, approved source documents, current candidate, and template catalog.

Allowed capabilities are narrowly scoped tools to:

- list approved source documents;
- extract text from an approved uploaded file;
- read the approved user profile and claim ledger;
- read the current candidate document;
- list template metadata;
- write a complete candidate JSON document;
- write structured claim proposals;
- request a deterministic preview render; and
- write the clean assistant reply or a structured reply field.

The agent is not allowed shell access, arbitrary filesystem access, direct database writes, snapshot or claim approval, remote asset access, email/application submission, or arbitrary HTML/JavaScript/CSS output.

Agent-provided IDs and references are treated as untrusted input. The backend resolves them inside the authenticated workspace, checks them against the session's permitted inputs, schema-validates every output, and rejects stale or unauthorized references.

## 11. Backend API

The target `/master-cv` API owns summary, templates, versions, candidates, sessions, structured block patches, source documents, portraits, preview/rendering, approval, and downloads:

```text
GET    /master-cv/summary
GET    /master-cv/templates
GET    /master-cv/approved
GET    /master-cv/versions
GET    /master-cv/sessions/{id}/status

POST   /master-cv/sessions/{id}/start
POST   /master-cv/sessions/{id}/messages
POST   /master-cv/sessions/{id}/finish
POST   /master-cv/sessions/{id}/reset

PUT    /master-cv/source-documents/{filename}
POST   /master-cv/portrait
POST   /master-cv/portrait/{asset_id}/crop

PATCH  /master-cv/candidates/{id}/blocks/{block_id}
POST   /master-cv/candidates/{id}/render
POST   /master-cv/candidates/{id}/approve
POST   /master-cv/claim-proposals/{id}/approve

GET    /master-cv/documents/{id}/preview
GET    /master-cv/documents/{id}/download
```

Equivalent existing endpoints may be retained during migration, but the public contract must cover every operation above consistently. Responses include stable IDs, lifecycle and review state, version/concurrency information, and structured errors. Binary preview/download endpoints return application-generated content and never accept raw HTML.

Approval is an authenticated user/backend operation. It validates schemas, references, review blockers, asset availability, template version, page count, overflow policy, and workspace ownership; creates immutable snapshots and generated Documents; and records audit events transactionally.

## 12. Frontend and application integration

### Master CV route

Add `/master-cv`, the left-navigation item, Master CV summary data to workspace loading, the responsive builder, template gallery, portrait editor, persistent block editing, comparison, version history, and explicit approval.

### Mission Control

Show Master CV readiness, **Continue Master CV** when a candidate exists, and review blockers as next actions. The absence of an approved Master CV does not block campaign creation while the neutral fallback is available.

### My story

Add a Master CV card linking to the builder, show which claim-ledger version the approved document uses, and route missing-fact corrections through the claim workflow.

### Documents

Pin the approved Master CV as a first-class document, show its HTML and PDF outputs, separate Master CV versions from tailored CVs, and link tailored outputs to the design snapshot used.

### Needs me

Create actionable exceptions for unsupported direct edits, proposed facts, broken portrait references, rendering overflow, stale edits, and candidates that cannot be approved.

Profile age is different from a factual or rendering blocker. When the latest approved user-profile and claim-ledger snapshots are older than the configurable refresh threshold (120 days by default), CV generation continues and creates one non-blocking **Needs me** suggestion for that approved snapshot pair. The user may open the onboarding recruiter to propose updates or dismiss the suggestion. Candidate changes do not affect tailoring until the user explicitly approves them into new immutable profile snapshots.

### Agent activity

Display Master CV preparation as a normal application-agent task with progress and a concise narrative.

### Onboarding integration

Persist eligible career documents and portraits into workspace-scoped assets, show the post-approval CTA, and preserve approved onboarding state if Master CV construction is deferred or abandoned.

## 13. Tailored CV and campaign integration

When a Master CV is approved, new campaigns pin its exact `MasterCvDocumentSnapshot`. Application packages record the same snapshot and the exact approved user-profile, claim-ledger, template, and portrait versions.

Tailored-CV runs receive:

- the approved user profile;
- the approved claim ledger;
- the campaign-pinned Master CV document specification;
- the exact template ID and version;
- the approved portrait variant and inclusion policy; and
- role and company context.

Tailoring may select or omit approved content, reorder sections, shorten wording, and emphasize relevant approved claims. It may not redesign the CV, change the portrait, add unsupported content, remove a required portrait contrary to explicit market/user policy, or silently switch template versions.

For tailored content, the current role begins by framing the broader system or business problem, then uses supported projects, metrics, lifecycle ownership, and tools. Skills stay to roughly 10–15 compact categories. Vacancy requirements map internally to approved claim IDs, with genuine evidence gaps retained as review information rather than invented content. Candidate-facing documents never mention ATS, keyword optimization, or similar tailoring mechanics.

Existing campaigns retain their pinned foundation. Updating an active campaign requires an explicit **Update campaign foundation** action that records the old and new snapshot IDs. Existing application packages remain reproducible from their original pins.

The repository-owned neutral template remains the fallback until an approved Master CV exists. The downstream resolver uses the campaign-pinned Master CV when present and otherwise uses the neutral fallback; it never silently adopts the latest global version for an already pinned campaign.

## 14. Implementation sequence

Each step must remain small, schema-validated, tested, and consistent with `docs/IMPLEMENTATION_PLAN.md`. Completed meaningful steps are committed independently with only their relevant paths.

1. **Planning contract and ADR:** finalize trust boundaries, lifecycle, schema ownership, fallback behavior, and acceptance criteria.
2. **Vendor upstream toolkit:** pin the complete repository, retain the license, and document updates and attribution.
3. **Schemas and persistence:** add or extend document, session, profile-asset, and claim-proposal contracts; migrations; immutable lifecycle transitions; workspace isolation; content hashes; and audit events.
4. **Template adapters and rendering:** normalize all thirteen templates to A4 and implement structured JSON-to-HTML/PDF rendering with sanitization, selectable-text, page-count, overflow, locale, and reproducibility checks.
5. **Portrait pipeline:** implement validated upload, metadata removal, normalization, immutable variants, cropping, policy, and workspace-scoped rendering.
6. **Backend API:** expose summary, catalog, sessions, source import, candidates, edits, render, versions, approval, and download with deterministic validation and concurrency handling.
7. **Agent runtime:** adapt the upstream workflow and route prompts, expose only restricted tools, validate structured output, and test prompt-injection and stale-reference defenses.
8. **Core workspace UI:** add navigation, responsive three-surface workspace, diagnostic chat, live preview, inspector, template gallery, and portrait editor.
9. **Editing and versions:** add durable block editing, review classification, compare, restore, lifecycle display, export, and approval.
10. **Onboarding and application integration:** add durable source reuse, post-onboarding CTA, Mission Control, My story, Documents, Needs me, agent activity, campaign pinning, and downstream tailoring.
11. **End-to-end hardening:** test security boundaries, malicious documents and prompt injection, cross-workspace access, image bombs, renderer isolation, overflow, snapshot reproducibility, fallback behavior, migrations, and responsive UI flows.

## 15. Completion criteria

The feature is complete only when a user can:

- upload an existing CV and optional portrait during onboarding or later;
- reuse those assets outside the onboarding run;
- open Master CV from the required left-navigation position;
- start through uploaded-CV, approved-profile, LinkedIn import, or existing-version routes;
- receive a focused diagnostic and work iteratively with the agent;
- preview their own validated content in all thirteen attributed templates;
- filter and switch templates without changing the approved version;
- crop, replace, remove, and safely reuse a portrait under an explicit inclusion policy;
- switch between supported one- and two-page output and resolve overflow;
- make durable direct edits with stable block and claim references;
- review all unsupported edits and proposed facts through the claim workflow;
- compare, restore, export, and explicitly approve an immutable Master CV version;
- find the approved version and its HTML/PDF outputs in Documents;
- continue to generate tailored CVs through the neutral fallback when no Master CV is approved;
- generate campaign-pinned tailored CVs that retain the approved design, template, and portrait policy; and
- reproduce exactly which user profile, claim ledger, Master CV document, template, portrait, campaign foundation, and renderer inputs produced every tailored document.

Completion also requires automated coverage for schema validation, lifecycle transitions, audit events, workspace isolation, rendering sanitization, template QA, portrait processing, agent tool restrictions, approval blockers, downstream pins, fallback behavior, and the principal desktop and mobile UI journeys.
