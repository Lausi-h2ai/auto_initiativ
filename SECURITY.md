# Security and privacy

Auto Initiativ processes career histories, contact information, and application drafts. Treat local databases, uploads, generated documents, agent runs, logs, and OAuth credentials as private.

## Safe local use

The example environment is for a loopback-only demonstration with authentication disabled. Keep the server bound to `127.0.0.1`. Shared deployments require authentication and per-user credentials. Research and drafting use configured external providers; local storage does not imply offline inference.

Email sending is disabled by default. Enabling a provider does not bypass deterministic validation, approval, dedupe, limits, transactional reservation, or auditing. Agents must never receive email credentials or call an email adapter.

## Reporting a problem

Do not put credentials, personal documents, private logs, or an exploitable vulnerability in a public issue. Use GitHub's private vulnerability reporting if it is enabled for the repository; otherwise request a private contact channel without posting sensitive details. Reproduce ordinary bugs with fictional data.

## Publication checks

- Review staged changes and every branch/tag that will be published, including author and committer metadata.
- Scan the entire reachable Git history with a dedicated secret scanner using redacted output. Also inspect personal names, email addresses, phone numbers, local paths, documents, image contents, and metadata; a secret scanner alone is not a PII audit.
- Keep `.env` variants, keys, tokens, databases, runs, artifacts, private evaluation corpora, and real-account screenshots out of Git. `.gitignore` does not remove files that were already committed.
- If sensitive material was committed, remove it from all affected history before publication. A later deletion or replacement does not erase earlier versions. Keep any recovery backup private and outside the material being shared.
- Revoke or rotate exposed credentials. History rewriting cannot revoke credentials or erase copies already held by others.
- Review the destination repository, old branches/tags, pull-request diffs, releases, and workflow artifacts before making an existing repository public. Local cleanup does not clean remote copies.

No automated scan proves the absence of all secrets or personal information. Record the scan scope and manually review exceptions before publishing.
