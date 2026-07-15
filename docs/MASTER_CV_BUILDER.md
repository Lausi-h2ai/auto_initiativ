# Master CV Builder

## Product outcome

The Master CV Builder creates the reusable, user-approved design and content source for later tailored CVs. It is a dedicated **Master CV** destination next to the user's profile and Documents; onboarding remains focused on collecting evidence and may hand off an uploaded CV and portrait to the builder.

The builder has three coordinated surfaces:

1. a focused design-and-content agent conversation;
2. a live A4 preview of the candidate document;
3. an inspector for Design, Content, Claims, Portrait, and Versions.

Desktop uses a 30/45/25 three-pane layout. Narrow screens use tabs and a bottom/drawer inspector. The user can begin from an approved profile, an onboarding CV upload, or an empty design.

## Authority boundaries

- `master_cv_profile.json` is the only factual claim source. The builder may omit, reorder, shorten, or propose corrections, but it may not invent claims.
- Agent output is candidate JSON validated by the backend. It cannot approve a claim or document, write database state, select arbitrary images, or emit executable HTML.
- The application owns template selection, portrait bytes, rendering, immutable version approval, audit events, and downstream pinning.
- A content block stores stable claim references. Unsupported text is marked `needs_review` and blocks document approval.
- Tailored CVs pin an approved master-CV snapshot, template revision, and portrait asset revision so output is reproducible.

## Upstream design assets

The MIT-licensed `yanliudesign/resume-builder-skill` repository is vendored at a pinned commit under `third_party/yanliudesign-resume-builder-skill/`. Its skill instructions, prompts, schema guidance, and templates are retained with attribution. Application-owned adapters expose the designs through a safe structured template catalog and normalize rendering to A4.

The initial catalog includes Atelier, Classic ATS, Editorial Banner, Elegant Serif, Executive, Ledger, Modern Sidebar, Photo Corporate, Photo Minimal, Pillar, Swiss, Tech Compact, and Timeline. Every adapter supports an optional portrait slot; German and Swiss market defaults prefer the portrait when one exists, while the user remains in control.

## Portrait safety

Portraits are first-class profile assets. Upload accepts JPEG, PNG, and WebP after checking the decoded format rather than trusting the filename. The backend normalizes orientation and color, removes EXIF metadata, stores a bounded application-owned derivative, and keeps crop/focal metadata separately. Renderers receive only a backend-produced image data URI for the selected profile asset. File URLs, network URLs, agent-selected images, and arbitrary data URIs remain forbidden.

## Version lifecycle

1. A builder session starts from the current approved claim snapshot and, when available, the latest approved master-CV document.
2. Agent proposals and direct edits update a candidate document snapshot through schema-validated block patches.
3. The preview renderer combines the structured candidate, an application-owned template adapter, and an approved portrait derivative.
4. Approval verifies every claim reference and all review flags, then creates an immutable approved version and a Documents entry.
5. Subsequent sessions branch from an approved version; approved versions are never mutated.

## API surface

The `/master-cv` router owns summary, template catalog, versions, candidates, structured block patches, portrait upload/crop, preview, approval, and builder-session chat. API responses contain stable IDs and review state. Binary preview/download endpoints are application-generated and never accept raw HTML.

## Acceptance criteria

- A user can start from an uploaded CV or approved profile, upload and crop a portrait, and iterate with the builder agent.
- All thirteen attributed templates are selectable and preview as A4 with optional portraits.
- Direct edits persist as structured blocks with claim references.
- Unsupported claims prevent approval and are visible in the Claims inspector.
- Approval creates an immutable, reproducible version visible in Documents.
- Tailoring can use only an approved master-CV version and preserves its pinned design and portrait unless the user explicitly selects a different approved option.
