# Public release readiness

Status: **source cleanup verified; publication history verification in progress**.

Do not publish the original repository history. A separate publication repository is being prepared under `artifacts/public-release/publication/`. No remote changes or push are authorized by this cleanup.

## Completed

- Product README, credential-free demo environment, contribution/security guidance, ignores and CI definitions.
- Fictional React and legacy UI examples, fictional live-test identity/company, and documented seeded dataset requirements.
- Removed fourteen unused imports and two unused assignments; fixed master CV session startup locale with a regression test.
- Rebuilt served frontend and restarted Auto Initiativ. Health and dashboard return HTTP 200; health reports dry-run and dashboard references the new bundle.
- Removed `Automode.pdf` from the index while preserving the ignored private local copy.
- Created and verified a complete private Git recovery bundle, source ZIP and staged/unstaged patches under `artifacts/public-release/recovery-20260907/`.
- Reviewed 1,099 historical blobs, 43 historical archive/review text versions, and all 14 upstream PNGs. No additional local-owner identifiers were identified beyond the targeted name/contact/document-path findings.
- Gitleaks 8.30.1 (download checksum verified) found no secrets in the original history. A separate local comparison read both configured credential JSON files and found no matches for three distinct actual secret values. Public OAuth endpoint URLs were excluded from the secret-value comparison. No confirmed credential exposure requires rotation from these findings.

## Verification

- Backend: 511 passed, six PostgreSQL tests skipped, 35 existing cookie deprecation warnings (326.58 seconds).
- Ruff, TypeScript, frontend build, live-test parsing, and diff whitespace checks pass.
- Independent code review found no critical or important defects.
- Disposable PostgreSQL verification and fresh-checkout demo verification are in progress.
- GitHub Actions has not run in this session.

## Remaining preparation

1. Commit the reviewed source cleanup.
2. Sanitize the separate publication clone: author/committer metadata, known owner names/contact information, historical document paths, and generated bundles; exclude `Automode.pdf`, `archive/`, and `reviews/` throughout history.
3. Scan all rewritten refs with Gitleaks and local credential/identifier comparisons; verify the documented demo from the fresh checkout and finish disposable PostgreSQL checks.
4. Record final evidence and commit the release-readiness documentation.

## Scope and limitations

- The original checkout, original history, recovery bundle, local credentials, databases, and run folders stay private. Share only reviewed publication refs, never the containing artifacts directory.
- Upstream source, MIT license and attribution remain intact. Its example contacts and portrait samples were reviewed for local-owner linkage; this is not certification that all upstream identities are fictional or independent verification of portrait rights.
- Fresh `npm ci` reports 11 dependency advisories (one low, four moderate, six high). These include development tooling and React Router. Dependency upgrades, including a suggested major Vite upgrade, are separate compatibility work; no production security clearance is claimed.
- No remote repository, cached pull request, release, workflow artifact, fork, or unreachable original Git object was audited or changed. Do not make an existing remote public based only on this local cleanup.
- The fictional document-library live test requires the dataset documented in CONTRIBUTING; this session validates parsing, not that preseeded scenario.
