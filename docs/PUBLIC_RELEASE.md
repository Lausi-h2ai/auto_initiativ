# Public release readiness

Status: **source cleanup and publication history verification complete; publication not yet performed**.

Do not publish the original repository history. A separate publication repository is prepared under `artifacts/public-release/publication/`. No remote was changed and no push was authorized by this cleanup.

## Completed

- Product README, credential-free demo environment, contribution/security guidance, ignores and CI definitions.
- Fictional React and legacy UI examples, fictional live-test identity/company, and documented seeded dataset requirements.
- Removed fourteen unused imports and two unused assignments; fixed master CV session startup locale with a regression test.
- Rebuilt served frontend and restarted Auto Initiativ. Health and dashboard return HTTP 200; health reports dry-run and dashboard references the new bundle.
- Removed `Automode.pdf` from the index while preserving the ignored private local copy.
- Created and verified a complete private Git recovery bundle, source ZIP and staged/unstaged patches under `artifacts/public-release/recovery-20260907/`.
- Reviewed 1,099 historical blobs, 43 historical archive/review text versions, and all 14 upstream PNGs. No additional local-owner identifiers were identified beyond the targeted name/contact/document-path findings.
- Gitleaks 8.30.1 (download checksum verified) found no secrets in the original history. A separate local comparison read both configured credential JSON files and found no matches for three distinct actual secret values. Public OAuth endpoint URLs were excluded from the secret-value comparison. No confirmed credential exposure requires rotation from these findings.

## Publication clone verification

- The publication clone under `artifacts/public-release/publication/` rewrites every commit to a single sanitized identity (`Auto Initiativ Contributors <contributors@example.invalid>`); the clone's local Git identity is pinned to the same value.
- `Automode.pdf`, `archive/`, and `reviews/` are absent from every ref and tree in the clone.
- A full-object audit of all reachable objects found no owner identifiers, no private document paths, and no excluded paths; the clone head tree matches the reviewed source HEAD tree except for the documented `.codex/config.toml` mail-server placeholder sanitization (evidence: `artifacts/public-release/rewritten-audit.json`).
- Gitleaks 8.30.1 found no secrets in all rewritten refs (evidence: `artifacts/public-release/gitleaks-after.json`). The scan used the 8.30.1 default ruleset, which intentionally allowlists values ending in `EXAMPLE`; 128 of 130 commits contain content and were all scanned (the other two are pure deletion commits whose removed content was covered by the full-object audit). A canary secret committed to a scratch clone was detected in both directory and git modes, confirming scan coverage.
- Fresh-checkout demo: clone, `npm ci`, Vite build, app start, health HTTP 200 reporting dry-run, dashboard HTTP 200 (evidence: `artifacts/public-release/fresh-checkout-verify-20260907-3/`). The first two clone attempts failed on a shell PATH issue for `git-upload-pack` and were superseded by the third attempt.
- Disposable PostgreSQL verification: fresh portable PostgreSQL 16.10 cluster on 127.0.0.1:55432; both PostgreSQL test files pass (6 passed); clean start and stop (evidence: `artifacts/postgres-portable-verify/verification-final-20260907.log`).

## Verification

- Backend: 511 passed, six PostgreSQL tests skipped (no local PostgreSQL in that run), 35 existing cookie deprecation warnings (326.58 seconds).
- Ruff, TypeScript, frontend build, live-test parsing, and diff whitespace checks pass.
- Independent code review found no critical or important defects.
- The six skipped PostgreSQL tests were subsequently executed against a disposable local PostgreSQL 16.10 cluster and all passed (see Publication clone verification).
- GitHub Actions has not run in this session; no remote was changed by this cleanup, so the CI jobs will first execute on the first push to a new publication repository.

## Preparation steps (all complete)

1. Commit the reviewed source cleanup. — Committed on `release/public-cleanup`.
2. Sanitize the separate publication clone: author/committer metadata, known owner names/contact information, historical document paths, and generated bundles; exclude `Automode.pdf`, `archive/`, and `reviews/` throughout history. — Completed and audited (see Publication clone verification).
3. Scan all rewritten refs with Gitleaks and local credential/identifier comparisons; verify the documented demo from the fresh checkout and finish disposable PostgreSQL checks. — Completed (see Publication clone verification).
4. Record final evidence and commit the release-readiness documentation. — Recorded in this document and in the implementation plan.

## Scope and limitations

- The original checkout, original history, recovery bundle, local credentials, databases, and run folders stay private. Share only reviewed publication refs, never the containing artifacts directory.
- Upstream source, MIT license and attribution remain intact. Its example contacts and portrait samples were reviewed for local-owner linkage; this is not certification that all upstream identities are fictional or independent verification of portrait rights.
- Fresh `npm ci` reports 11 dependency advisories (one low, four moderate, six high). These include development tooling and React Router. Dependency upgrades, including a suggested major Vite upgrade, are separate compatibility work; no production security clearance is claimed.
- No remote repository, cached pull request, release, workflow artifact, fork, or unreachable original Git object was audited or changed. Do not make an existing remote public based only on this local cleanup.
- The fictional document-library live test requires the dataset documented in CONTRIBUTING; this session validates parsing, not that preseeded scenario.
