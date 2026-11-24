# TenderGraph v1 — free-first handoff and deferred release gates

Scope frozen in [RELEASE_SCOPE.md](RELEASE_SCOPE.md). No feature expansion outside
the seven phases. Current objective: a local release candidate; public launch is
not complete merely because code and CI pass.

## Free local acceptance

1. Preserve the current Mac working tree; inspect `git status` before pulling.
   Use a clean checkout or fast-forward only. Do not reset uncommitted work.
2. Preserve the existing .env and database volume. Run `uv sync --frozen`,
   `make db-up`, `make db-health`, `make check`, and `make package`.
3. Run a recent TED refresh with a small explicit date window and intended
   countries. Backfill older windows in bounded, serial batches as needed.
   Do not claim coverage of all Europe from a few windows.
4. Run `make history-index HISTORY_LIMIT=20` to enrich a bounded set of indexed
   result notices. This calls official public TED XML, not a paid service.
   Missing, failed or unsupported sources are not inferred as winners.
5. Run `make serve` and exercise profile → matches → save → alerts →
   notice/package evidence → decision dossier → buyer history → export.
   Use a registered test account and a second account to check isolation.
6. Run `make db-backup`, then `make db-restore-check BACKUP=data/backups/<file>.dump
   RESTORE_DB=restore_check_v1`. The target must be a new database. Compare row
   counts and inspect restored product state, document data, search indexes and
   pgvector availability; remove the disposable database only after approval.
7. Record CI URL, live dataset dates/countries/counts, observed errors, actual
   restore evidence and browser screenshots. Do not substitute synthetic CI data
   for a real TED or production acceptance test.

Backups contain account information, password hashes and procurement data.
Keep restricted, encrypted off-host copies when deployment is approved; do not
commit backups, .env, document caches or source data. A database dump alone does
not back up raw document files, audit artifacts, scheduler config or model cache.

## Phase 5 — beta protocol (no paid acquisition)

Recruit 5–10 consenting IT/data/software SMEs through the owner's existing
network. Use controlled demonstrations or a secure, approved test environment.
Do not expose a local developer machine to the internet.

For each tester, record date, anonymized tester ID, sector, profile task result,
whether they found and saved a genuinely relevant tender, whether source evidence
was correct, whether they could finish a bid/no-bid review unaided, time taken,
friction, return usage, willingness to pay, and bugs. Ask for explicit consent
to record feedback; avoid collecting unnecessary personal or sensitive information.

Proposed acceptance thresholds (not observed results): at least five completed
sessions; at least four of five able to finish the main workflow unaided; at least
three identify a genuinely useful opportunity; no unresolved critical security,
data-loss or misleading-evidence issue. Recheck any reported serious defect.
If tests are not yet done, phase 5 remains pending. No invented participants.

## Phase 6 — public deployment after the break

Do not activate hosting, buy a domain, expose a port, or sign up for a paid
service until the owner approves. Choose a small measured deployment after
benchmarking actual CPU/RAM/disk requirements. Keep database private; serve
through TLS reverse proxy with exact Host and Origin preservation, ingress
request limits, per-IP limits, concurrency limits and trusted proxy rules.

Public preview controls are opt-in via `TENDERGRAPH_PUBLIC_ORIGIN=https://...`.
Set `RAG_PROVIDER=evidence`. Anonymous local accounts, local-account claiming,
OpenAPI docs and public on-demand procurement-document ingestion are disabled.
Existing read-only indexed document evidence remains available after sign-in.
Use a separate isolated operator process for document enrichment; enabling public
fetching requires network egress isolation and DNS-rebinding/redirect validation.
The current DNS precheck is not a pinned-IP transport.

The in-process limiter is global to one worker, not a distributed rate limiter.
Set a 1 MiB body limit at the proxy, per-IP authentication limits, API concurrency
limits, timeouts, and monitor false positives. Keep one API worker until load
testing and shared limits are designed. Do not trust arbitrary forwarded headers.
Test HTTPS, cookies, cross-origin writes, registration/login/logout, account
isolation, two-tab updates, rate limits, backup/restore and refresh failure.
Browser state remains local-first: same-item concurrent edits are last-writer-wins;
public beta must assess this limitation.

Before public launch: review personal-data processing and retention, GDPR
rights/deletion/export procedure, privacy notice, terms, public data reuse
conditions, security vulnerability/dependency review, operational secrets,
database privileges, recovery/monitoring, actual capacity, and incident response.
Real live verification and any necessary independent security review remain gates.
Record approval and a rollback target; tag v1.0 only after release acceptance.

## Phase 7 — monetization last

Defer all billing integration, payment-provider activation, pricing commitment and
paid subscriptions until owner approval and beta/deployment gates. Pricing is a
hypothesis, not a verified market result. Confirm Belgian business/tax/VAT,
invoicing and applicable consumer/business obligations with qualified advice.
When authorized, use provider test mode first: creation, successful payment,
renewal, failed payment, cancellation, refund, webhook signature/idempotency,
account entitlement changes and invoice records. Do not collect card details
directly. Go live only after acceptance and explicit approval.

The commercial goal is a secure accessible product that actual SMEs use and
at least one real customer pays for. First payment is a business milestone, not
something CI can verify. After the pause, finish only the listed release gates;
no new roadmap expansion.
