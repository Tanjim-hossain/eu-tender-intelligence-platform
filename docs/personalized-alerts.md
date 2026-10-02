# Personalized tender alerts

TenderGraph alerting turns the existing company profile and matching engine into a persistent, deduplicated opportunity digest.

## Product behavior

A refresh evaluates the current company profile against the loaded TED search index and keeps candidates only when they:

- were published inside the configured recent-notice window;
- meet the account's minimum profile-fit score;
- do not have a closed deadline according to the current matching signal;
- are not already saved or ignored in the account's opportunity state.

Each `(account_id, publication_number)` can become an alert only once. Re-running refresh therefore does not create duplicate alerts, including when the same notice remains inside the lookback window for several days.

Alert events persist the scored match snapshot used when the tender was detected. A later change to the company profile does not rewrite historical alert evidence.

## Preferences

Defaults:

- enabled: `true`
- minimum fit score: `70`
- lookback window: `14` days
- digest size: `10` items

Preferences live in PostgreSQL under `product.alert_preferences`. Detected opportunities live in `product.alert_events`.

## API

- `GET /alerts/accounts/{account_id}/preferences`
- `PUT /alerts/accounts/{account_id}/preferences`
- `GET /alerts/accounts/{account_id}/digest`
- `POST /alerts/accounts/{account_id}/refresh`
- `POST /alerts/accounts/{account_id}/items/{publication_number}/seen`
- `POST /alerts/accounts/{account_id}/seen-all`

The same product-account authorization boundary used by persisted profile and opportunity state applies to alert endpoints. Registered accounts require their authenticated session; local accounts retain local-first compatibility.

## Batch refresh

Once an account has persisted enabled alert preferences, all enabled accounts can be refreshed with:

```bash
uv run python scripts/refresh_tender_alerts.py
```

A specific account can be refreshed with:

```bash
uv run python scripts/refresh_tender_alerts.py --account-id <uuid>
```

This command is deliberately delivery-provider agnostic. It can be called by cron, launchd, systemd timers, or a future deployment scheduler without requiring a paid email/SMS service.

## v1 boundary

This phase creates and persists the personalized digest but does not send external email, SMS, or push notifications. It also does not claim that every relevant tender in TED is discovered: matching is bounded by the existing hybrid retrieval candidate depth. Users should continue to verify fit, eligibility, deadlines, and procurement requirements against the official notice and tender documents.
