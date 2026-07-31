# Cost ledger

Tracks Decision 11 (zero recurring cost) against measured reality. Every
phase that touches one of these components records its measurement here.
Any row above 50% of its free allowance is a design problem to fix before
it becomes a billing problem — see Part I2.

## Decision 11 components

| Component                           | Service                       | Free allowance                                                     | Expected single-user load    | Measured usage                                     | Measured on | No card on file? |
| ----------------------------------- | ----------------------------- | ------------------------------------------------------------------ | ---------------------------- | -------------------------------------------------- | ----------- | ---------------- |
| PWA hosting                         | Cloudflare Pages              | Unlimited bandwidth, 10 GB storage, 20,000 files, 500 builds/month | < 20 MB, < 30 builds/month   | — not yet measured (Pages project not created)     | —           | —                |
| Sync + calendar proxy + push sender | Cloudflare Workers            | 100,000 requests/day, 10 ms CPU per invocation                     | < 2,000 requests/day         | — not built until Phase D                          | —           | —                |
| Server database                     | Cloudflare D1                 | 5 GB storage, 5M rows read/day, 100k rows written/day              | < 50 MB, < 3,000 writes/day  | — not built until Phase D                          | —           | —                |
| Scheduled jobs                      | Workers Cron Triggers         | 5 triggers/account, 3/Worker                                       | 2 triggers                   | — not built until Phase D/H3                       | —           | —                |
| Backup storage                      | Cloudflare R2                 | 10 GB storage, free egress to Workers                              | < 100 MB                     | — not built until Phase I1                         | —           | —                |
| TLS + domain                        | `*.pages.dev` subdomain       | Included, HTTPS automatic                                          | 1 subdomain                  | — not yet provisioned                              | —           | —                |
| Calendar                            | Google Calendar API           | 1,000,000 queries/day, no billing at any volume                    | < 300 queries/day            | — not built until Phase C3                         | —           | —                |
| Push delivery                       | Web Push / VAPID              | Self-signed keys, no service, no account                           | Capped at 2/day (Decision 6) | — not built until Phase H3                         | —           | —                |
| Source + CI                         | GitHub free tier              | Private repos, 2,000 Actions minutes/month                         | < 200 minutes/month          | — not yet measured (workflow created, has not run) | —           | —                |
| Toolchain                           | Node, pnpm, Vite, SQLite WASM | Open source                                                        | —                            | Node 26.4.0, pnpm 11.18.0, Vite 8.2.0              | 2026-07-31  | n/a              |

## Account confirmations

| Account      | Created                                 | No card on file confirmed                                                            | Notes                                                 |
| ------------ | --------------------------------------- | ------------------------------------------------------------------------------------ | ----------------------------------------------------- |
| Cloudflare   | ☐ not yet                               | ☐                                                                                    | Blocks Pages hosting, and everything in Phase D/H3/I1 |
| Google Cloud | ☐ not yet                               | ☐                                                                                    | Blocks Phase C3 Calendar API                          |
| GitHub       | already exists (`Nox-eturnus/Projects`) | n/a (no billing risk from Actions on a free-tier private repo under the minutes cap) | Actions workflow added; has not run yet               |

## Notes

- The GitHub Actions workflow (`.github/workflows/life-helper-verify.yml`)
  is scoped to `Life_Helper/**` via a `paths` filter so unrelated changes
  elsewhere in this monorepo don't burn Actions minutes.
- Every row that says "not yet" is expected at this point in the plan —
  Part A1 only requires the toolchain and hosting scaffolding to exist and
  the accounts to be confirmed free. Populate the remaining rows as each
  phase builds the component and measures it against its dashboard.
