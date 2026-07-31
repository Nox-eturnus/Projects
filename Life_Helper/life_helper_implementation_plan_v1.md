# Life Helper — Personal Task, Routine, Project, People, and Notes System — Overall Plan (v1)

This plan builds a single-user, local-first, offline-capable personal operating system covering seven pillars: frictionless capture, a Today dashboard, routines and streaks, projects and retainers, a personal CRM, a notes library, and cross-cutting infrastructure (search, notifications, re-entry).

The project is framed as a tool that must survive being ignored. The primary risk is not missing features — it is abandonment. Every phase gate is therefore a usage gate, not only a correctness gate.

**Total recurring cost is zero.** Build, hosting, storage, sync, calendar access, and push notifications all run inside permanent free tiers with no credit card, no trial period, and no expiry. Decision 11 makes this binding and lists every component with its limit and measured headroom.

## How to use this plan

Work through Phases A–I in order. Phase J is optional and is not a prerequisite for anything.

Phases A–C produce a single-device system that is genuinely usable. Phase D adds multi-device sync. Phases E–G add the remaining pillars. Phase H makes the whole thing coherent. Phase I hardens it.

Parts inside a phase may be built in any order unless a prerequisite is stated. Phases may not be reordered — in particular, do not build Phases E–G before Phase D, because retrofitting sync onto seven pillars of schema is far more expensive than onto two.

Do not start a new phase until the previous phase's usage gate has passed. A phase that is built but not used is a phase that has failed, regardless of test coverage.

### Runtime invariant

All development, test, build, and migration commands run against the pinned toolchain declared in Phase A1:

- Node.js pinned via `.nvmrc` and enforced by `engines` in `package.json`
- package manager: `pnpm`, version pinned via `packageManager` field
- TypeScript in `strict` mode; `any` requires an inline justification comment
- one command runs everything: `pnpm verify` = typecheck + lint + unit + integration + build

Before continuing a phase, verify the toolchain:

```bash
node --version
pnpm --version
pnpm verify
```

No phase is complete while `pnpm verify` is failing. Do not add a phase's work on top of a red build.

### Definition of "used"

Several gates below require a period of real usage. Usage means: the app was opened on at least 5 of 7 consecutive days, on at least two different days from a phone, and at least one item was captured or completed on each of those days. Self-reported is fine — this is a personal project — but record it in `docs/usage_log.md` with dates, or the gate has not passed.

---

## Design decisions

### 1. One entity spine

Every user-visible object — task, note, journal entry, highlight, quote, person, project, retainer, routine — is a row in a single `items` table with a `kind` discriminator, plus a typed side table for kind-specific fields.

A single `links` table (`from_id`, `to_id`, `rel`) expresses every relationship: task→project, note→person, task→person, note→note.

This is the decision that makes the seven pillars one product instead of seven apps. Global search, backlinks, resurfacing, and the re-entry screen are each written once against the spine rather than seven times against seven schemas.

Do not add a top-level table for a new pillar. If a new pillar seems to need one, it is a new `kind` plus a side table.

### 2. Sync-ready from day one, sync engine in Phase D

The schema and every write path must be sync-compatible starting in Phase A, even though no sync code exists until Phase D. Concretely, from Phase A onward:

- every entity has a UUIDv7 primary key generated on the client, never an autoincrement integer
- every mutation appends a row to an append-only `ops` log; the UI reads from materialized tables, but those tables are always derivable by replaying `ops`
- every op carries a Hybrid Logical Clock timestamp and an originating `device_id`
- deletes are tombstones (`deleted_at`), never `DELETE FROM`
- no mutation is destructive-in-place; conflicting field writes must be resolvable by last-writer-wins per field

Violating this in Phases A–C makes Phase D a rewrite. This is the single most consequential rule in the plan.

### 3. Capture never blocks

The capture path has exactly one required field: the raw text. No project, no due date, no priority, no type selection, no tag. Everything else is inferred or deferred.

Capture must complete and be durably written in under 200ms from keypress to persisted, offline, with no network. Cleanup happens later in a separate batch ritual, never as a tax at capture time.

If a proposed feature adds a required field, a modal, a confirmation, or a network round trip to capture, it does not ship.

### 4. Everything decays

The system must not accumulate without bound. Backlogs that only grow are the direct cause of abandonment.

- every task carries a `touch_count` (incremented on every deferral or reschedule) and a `last_touched_at`
- items untouched beyond a configurable threshold (default 30 days) become eligible for amnesty
- amnesty moves items to a `someday` tier; it never deletes them and never asks for a reason
- the someday tier is not shown on Today and does not count toward any badge or overdue total

No view in the app displays a raw unbounded count of outstanding work. Counts are always scoped to a horizon.

### 5. Deterministic first, AI as a confirmed fallback

Capture parsing is rule-based: dates and times, `@person`, `#project`, `!priority`, `*routine`, and a leading `?` for open questions. Rules run locally, offline, with zero latency and zero cost.

A model is invoked only in Phase J, only on input the rules could not parse, only through your own Worker, and only with its output presented as an editable suggestion that the user confirms before it commits. A model never writes directly to the database and never mutates an existing item.

If Phase J is never built, the system is complete and fully functional.

### 6. Notification budget is a hard cap

Maximum two push notifications per day, enforced in code at the send site, not by convention. The budget is a counter checked before every send, reset at local midnight.

If more than two notifications qualify on a given day, they are merged into one digest. A muted app is a dead app, and the cap exists to prevent the user from ever reaching for the mute switch.

### 7. Every feature ships with an empty state and a re-entry story

No view is complete until three states are implemented and reviewed:

- **empty** — the user has no data yet; the screen explains what would appear here and offers one action
- **cold** — the user has been away 3+ days; the screen does not display red badges, overdue counts, or guilt language
- **loaded** — normal operation

A view with only the loaded state is not done. This is checked explicitly in every Definition of Done that includes UI.

### 8. Privacy boundary

Declare and enforce what leaves the device:

- item content never leaves the device except as encrypted op payloads relayed through your own Cloudflare Worker
- op values are encrypted client-side with a key derived from a passphrase held only on paired devices; the Worker and D1 never hold the key and never see plaintext
- Google Calendar access is read-only scope (`calendar.readonly`); the app never writes to the calendar
- no analytics, no telemetry, no crash reporting to third parties
- in Phase J, only the unparsed capture fragment is sent to a model — never the surrounding item, never linked people, never note bodies

Any change to this boundary is a design change and must be recorded here before it is implemented.

### 9. Performance budgets

Declared before implementation, measured in Phase I, and treated as regressions if exceeded:

- capture keypress → persisted: < 200ms offline
- app cold start → Today rendered: < 1.5s on a mid-range Android device
- global search keystroke → results: < 100ms at 10,000 items
- Today view render: < 50ms at 500 active tasks

### 10. Single user, no multi-tenancy

There is one user. There is no registration, no password reset, no email verification, no roles, no sharing, no collaboration, no billing.

Device authentication is a one-time pairing code that issues a long-lived device token. Do not build OAuth, do not build a user table with a foreign key on every row, do not build an invite flow. Every hour spent on multi-tenancy is an hour not spent on the thing that gets used.

If this ever becomes a product, that is a new plan with a migration phase. It is not this plan.

### 11. Zero cost is a binding constraint

The system must cost nothing to build, host, run, or use — permanently. Not a free trial, not a promotional credit, not a tier that expires. If a component cannot run inside a permanent free allowance, it does not enter the plan.

The pinned free stack, verified July 2026:

| Component | Service | Free allowance | Expected single-user load |
|---|---|---|---|
| PWA hosting | Cloudflare Pages | Unlimited bandwidth, 10 GB storage, 20,000 files, 500 builds/month | < 20 MB, < 30 builds/month |
| Sync + calendar proxy + push sender | Cloudflare Workers | 100,000 requests/day, 10 ms CPU per invocation | < 2,000 requests/day |
| Server database | Cloudflare D1 | 5 GB storage, 5M rows read/day, 100k rows written/day | < 50 MB, < 3,000 writes/day |
| Scheduled jobs | Workers Cron Triggers | 5 triggers per account, 3 per Worker; invocations count against the request quota | 2 triggers |
| Backup storage | Cloudflare R2 | 10 GB storage, free egress to Workers | < 100 MB |
| TLS + domain | `*.pages.dev` subdomain | Included, HTTPS automatic | 1 subdomain |
| Calendar | Google Calendar API | 1,000,000 queries/day, no billing at any volume | < 300 queries/day |
| Push delivery | Web Push / VAPID | Self-signed keys, no service, no account | Capped at 2/day by Decision 6 |
| Source + CI | GitHub free tier | Private repos, 2,000 Actions minutes/month | < 200 minutes/month |
| Toolchain | Node, pnpm, Vite, SQLite WASM | Open source | — |

Rules that follow from this:

- **No custom domain.** A domain is the only unavoidable recurring cost in a typical deployment, and `app-name.pages.dev` is functionally identical for a single user. Do not buy one.
- **No credit card on file anywhere.** Cloudflare's free tier and Google Cloud's Calendar API both work without billing enabled. If a service asks for a card to proceed, that service is disqualified.
- **The Worker stays dumb.** The 10 ms CPU ceiling on the free plan is a real limit. The Worker relays encrypted ops, proxies calendar reads, and signs VAPID tokens — nothing else. All application logic runs on the client. This is a healthy constraint: it enforces the local-first architecture that Decision 2 already requires.
- **Every phase records its measured usage** against the table above in `docs/cost_ledger.md`. If any component exceeds 50% of its free allowance, that is a design problem to solve before it becomes a billing problem.
- **Free tiers change.** The mitigation is architectural, not contractual: because every device holds a complete local replica (Decision 2) and Part I1 provides full export, losing a free tier costs you sync, never data. Migrating the Worker and D1 to another free host is a weekend, and the plan is deliberately structured so nothing else depends on the choice.

Anything with a per-use price — hosted AI inference, transcription APIs, managed Postgres, error-tracking services, a Play Store developer account — is out of scope unless it has a permanent free allowance sufficient for single-user load. Phase J calls this out explicitly where it applies.

### 12. Stop and pivot rules

- If capture latency exceeds the Decision 9 budget, stop feature work and fix it. Slow capture kills the whole system.
- If a usage gate fails twice, do not proceed to the next phase. Diagnose why the built feature is not being opened, and cut or redesign it. Building more on top of an unused foundation compounds the problem.
- If the sync engine produces a divergence in Phase D4 that is not reproducible, stop and add op-log tracing before continuing. Never ship a sync engine with an unexplained divergence.
- If a pillar in Phases E–G proves unused after its gate, mark it dormant and move on rather than expanding it. A dormant pillar is a valid outcome and a useful finding.
- If Google Calendar OAuth becomes a blocker, ship Phase C without capacity computation and treat calendar as a Phase D-parallel task. Do not let a third-party API block the first pillar.
- If any component in the Decision 11 table starts requiring payment, a credit card, or drops below single-user viability, stop and migrate that one component. Do not accept "just a couple of dollars a month" — the zero-cost property is a design constraint, and the local-first architecture makes migration cheap precisely so this rule can be enforced.

---

## Surface legend

| Tag | Surface | Role |
|---|---|---|
| PWA | React + TypeScript PWA on Cloudflare Pages | The application; installs on Android, desktop, runs on web |
| DBW | Web Worker in the browser | SQLite WASM + OPFS; all local database access |
| SW | Service worker | Offline shell, push receipt, background sync trigger |
| EDGE | Cloudflare Worker + D1 | Sync relay, Google Calendar proxy, push sender; dumb by design |
| LOCAL | Developer machine | Build, test, migration authoring |
| EXT | Third-party API | Google Calendar (read-only), Web Push (VAPID) |

`DBW` (browser Web Worker running SQLite) and `EDGE` (Cloudflare Worker) are different things despite both being called "workers" in their respective docs. The plan uses these tags to keep them distinct.

---

# PHASE A — Foundations

## Part A1 — Repository, toolchain, and verification harness

Deliverable: working repository with a green `pnpm verify`; `docs/phase_A1_toolchain.md`; `docs/cost_ledger.md` seeded with the Decision 11 table and empty measurement columns.

Set up:

- Vite + React 18 + TypeScript strict
- `vite-plugin-pwa` with Workbox, manifest, icons, install prompt
- Vitest for unit and integration tests, Playwright for end-to-end
- ESLint + Prettier, enforced in `pnpm verify`
- a single `pnpm verify` script chaining typecheck, lint, test, and build
- pinned Node via `.nvmrc`, pinned pnpm via `packageManager`
- GitHub Actions running `pnpm verify` on push, with a concurrency group so superseded runs cancel — this keeps a private repo comfortably inside the 2,000 free Actions minutes per month
- Cloudflare Pages connected to the repo for automatic deploys on push to `main`

Create the free accounts this phase depends on — Cloudflare and Google Cloud — and confirm both are usable with no billing enabled and no card on file. If either demands payment details to proceed, stop and record the blocker before writing further code; it invalidates Decision 11 and the hosting choice must be revisited first.

Definition of Done: a clean clone runs `pnpm install && pnpm verify` successfully on a machine with only Node installed; the PWA installs on an Android device from the deployed Pages URL over HTTPS; the install prompt appears and the app launches standalone; `docs/cost_ledger.md` exists with every Decision 11 row and an explicit "no card on file" confirmation for each account; the Pages deploy is automatic and green.

## Part A2 — Data model and migration system

Deliverable: `src/db/schema.sql`, `src/db/migrations/`, `docs/phase_A2_data_model.md`.

Define the entity spine:

```text
items(
  id TEXT PRIMARY KEY,            -- UUIDv7, client-generated
  kind TEXT NOT NULL,             -- task|note|person|project|retainer|routine
  title TEXT NOT NULL,
  body TEXT,
  status TEXT,                    -- kind-specific vocabulary
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  deleted_at INTEGER,             -- tombstone; never hard delete
  hlc TEXT NOT NULL,              -- last-write HLC timestamp
  origin_device TEXT NOT NULL
)

links(from_id, to_id, rel, created_at, deleted_at, hlc, origin_device)
tags(item_id, tag, hlc, origin_device)

task_fields(item_id, due_at, scheduled_for, estimate_min,
            touch_count, last_touched_at, someday, completed_at,
            energy, next_action)
routine_fields(item_id, cadence, time_block, grace_budget_per_month,
               paused_until)
container_fields(item_id, container_kind, definition_of_done,
                 cycle_start, cycle_end, budget_hours, budget_scope)
person_fields(item_id, cadence_days, last_contact_at, next_contact_due)
note_fields(item_id, note_kind, source, resurface_after, resurface_count)

ops(
  op_id TEXT PRIMARY KEY,
  entity_id TEXT NOT NULL,
  entity_table TEXT NOT NULL,
  field TEXT NOT NULL,
  value TEXT,
  hlc TEXT NOT NULL,
  device_id TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  synced_at INTEGER
)

items_fts USING fts5(title, body, content='items', content_rowid='rowid')
```

Write forward-only numbered migrations. Every migration has a test that runs it against a fixture database and asserts the resulting schema.

Definition of Done: migrations run cleanly from empty to head; a fixture database with one row of every `kind` round-trips; FTS5 returns a hit for a body-text query; every table carries `hlc` and `origin_device`; no autoincrement integer primary key exists anywhere; a test asserts that no code path issues `DELETE FROM` against `items`, `links`, or `tags`.

## Part A3 — Local database layer and reactive query API

Deliverable: `src/db/worker.ts`, `src/db/client.ts`, `src/db/ops.ts`, `docs/phase_A3_db_layer.md`.

Implement:

- SQLite WASM (`@sqlite.org/sqlite-wasm`) running in a Web Worker with the OPFS VFS for durable persistence
- a typed RPC bridge from the main thread to the worker (Comlink or a hand-rolled `postMessage` protocol)
- `mutate()` — the single write entry point; every write appends to `ops` and updates the materialized table in one transaction
- `useQuery()` — a React hook that re-runs a query when any of its dependent tables change
- Hybrid Logical Clock implementation with monotonic guarantees across reloads (persist the last HLC)
- `device_id` generated once and persisted in OPFS

Definition of Done: data survives a hard browser restart and an OS restart; every write produces exactly one `ops` row per changed field; replaying `ops` from empty into a fresh database reproduces the materialized tables byte-identically (this is an automated test and is the foundation of Phase D); the HLC never goes backwards across a reload; concurrent writes from two tabs do not corrupt the database.

## Part A4 — Design system and shell

Deliverable: `src/ui/` primitives, `docs/phase_A4_design_system.md`.

Build the minimum: type scale, spacing scale, color tokens with dark mode, buttons, inputs, list rows, sheets, and an app shell with navigation. Keyboard focus states are required, not optional.

Define the three-state pattern from Decision 7 as a reusable component contract so every subsequent view inherits it.

Definition of Done: a component gallery route renders every primitive in light and dark mode; keyboard tab order is correct through the shell; the shell renders correctly at 360px width and at 1920px; no color is hardcoded outside the token file.

---

# PHASE B — Capture

The vertical slice. This phase proves the whole architecture end to end on the narrowest possible feature.

## Part B1 — Capture surface

Deliverable: capture route and component; global capture shortcut.

One text input. Submit on Enter, newline on Shift+Enter. Writes to `items` with `kind='task'` and `status='inbox'`, then clears and stays focused for the next capture.

Bind a global shortcut (`Ctrl/Cmd+K` or `Ctrl/Cmd+N`) that opens capture from anywhere in the app.

Add a large microphone button that invokes the platform's native dictation via the input's `enterkeyhint` and the system keyboard. Do not implement speech recognition, do not bundle a model, do not call a transcription API — Android's keyboard dictation is already excellent, free, and offline.

Definition of Done: capture works fully offline with the network disabled; keypress-to-persisted is under 200ms measured on a mid-range Android device; the input never loses focus between consecutive captures; dictation produces text in the field on Android; all three view states from Decision 7 are implemented.

## Part B2 — Deterministic parser

Deliverable: `src/capture/parse.ts` and its test suite.

Parse from raw text, in order:

- dates and times: `today`, `tomorrow`, `mon`–`sun`, `next week`, `3pm`, `15:00`, `21/8`, `in 3 days`, `every monday`
- `@name` → person reference
- `#project` → container reference
- `!` / `!!` / `!!!` → priority
- `*` prefix → routine
- `?` prefix → open question, filed as a note rather than a task
- `~45m` / `~2h` → estimate

Unmatched text remains the title. The parser is pure, synchronous, and has no I/O.

Parsed tokens render as removable chips under the input before submit, so the user can see and reject any interpretation.

Definition of Done: a test table of at least 60 input strings maps to expected parse output; the parser is pure and dependency-free; ambiguous input (`5/6`) resolves by a documented and tested rule; every parse result is visible as a chip and individually removable before commit; unparsed input still produces a valid item.

## Part B3 — Inbox and triage ritual

Deliverable: inbox route; triage flow.

The inbox lists everything with `status='inbox'`, newest first. Triage presents one item at a time with a small fixed set of actions: schedule for today, schedule for a date, file to a project, convert to note, convert to routine, someday, done, delete.

Triage is keyboard-driven on desktop (single-key bindings) and swipe-driven on mobile.

Definition of Done: an inbox of 20 items can be fully triaged in under 90 seconds using only the keyboard; every action is undoable for 10 seconds via a toast; leaving triage mid-way loses nothing; all three view states are implemented.

## Part B4 — Capture gate

Hard gate. Fixed before execution and not negotiable after.

- capture latency budget met on a real Android device, measured and recorded
- `ops` replay test passes (Part A3) with real captured data, not fixtures
- the app has been installed to the Android home screen and used from there, not from a browser tab
- **usage: 7 consecutive days meeting the Definition of "used" above**
- at least 30 real items captured, not test data

Definition of Done: all conditions pass and are recorded in `docs/usage_log.md`. If the usage condition fails, do not proceed to Phase C — diagnose the friction, fix it, and re-run the gate.

---

# PHASE C — Today dashboard

The first pillar. This is the screen that has to earn a daily open.

## Part C1 — Task scheduling model

Deliverable: scheduling logic and its tests.

Distinguish three date concepts and never conflate them:

- `due_at` — a real external deadline; missing it has consequences
- `scheduled_for` — the day you intend to do it; freely moved without penalty
- `defer_until` — hidden from all views before this date

Moving `scheduled_for` forward increments `touch_count` and updates `last_touched_at`. Moving `due_at` does not — a deadline change is external, a reschedule is a choice.

Definition of Done: the three fields are independently settable and tested; rescheduling increments touch count exactly once per move; deferred items are absent from every view until their date; timezone handling is tested across a DST boundary.

## Part C2 — Top 3 and evening shutdown

Deliverable: Today route; shutdown route; notification hook.

Today displays exactly three committed tasks, prominently, above everything else.

The top 3 are selected the previous evening through a shutdown ritual: a short flow that reviews what got done, then picks tomorrow's three. Triggered by the day's first notification slot (Decision 6), default 8pm, configurable.

If shutdown was skipped, Today proposes three — drawn from due today, then slipping, then oldest scheduled — and asks for one tap to accept or swap.

Below the top 3, the rest of the day's scheduled work appears in a visually secondary list.

Definition of Done: the shutdown flow completes in under 60 seconds; skipping shutdown produces a sensible proposal rather than an empty screen; the top 3 persist across reloads and are scoped to a specific date; completing all three produces a clear finish state rather than immediately surfacing more work; all three view states are implemented.

## Part C3 — Google Calendar (read-only) and capacity

Deliverable: `EDGE` OAuth flow and calendar proxy; client event cache; capacity computation.

The Worker holds the Google refresh token as a Wrangler secret and exposes a normalized read-only event feed. The client caches events locally so Today renders offline from the last sync.

Poll on app focus and at most every 15 minutes, never on a background timer. At that cadence the Calendar API sees a few hundred queries a day against a 1,000,000/day free allowance, and the Worker requests stay inside the Decision 11 budget.

Compute free capacity: waking hours minus events minus a configurable buffer, displayed on Today as available minutes. Compare it against the sum of estimates on the top 3 and warn when the commitment exceeds the capacity.

Scope is `calendar.readonly`. The app never writes to Google Calendar.

Definition of Done: OAuth completes and the refresh token survives a Worker redeploy; events render on Today; capacity is computed and displayed; the token is never present in client-side storage or in the repository; Today renders fully offline from cache with a visible staleness indicator; a revoked token produces a clear reconnect prompt rather than a crash.

## Part C4 — Slipping view

Deliverable: slipping route and detection logic.

Flag tasks by `touch_count` first and age second. A task deferred four times is a stronger signal than a task that has sat untouched for twelve days — the former is either unimportant or badly defined.

Each slipping item offers exactly three actions: **do it now** (pull into today's top 3), **break it down** (create subtasks and archive the parent), **kill it** (someday or delete).

Definition of Done: slipping ranks by touch count with age as a tiebreaker, and this is tested; each of the three actions works and is undoable; the view is empty and encouraging rather than alarming when nothing is slipping; language contains no guilt framing — reviewed explicitly against Decision 7.

## Part C5 — Amnesty and decay

Deliverable: amnesty flow; someday tier; decay job.

A single control sweeps everything untouched beyond the threshold into the someday tier. It asks for confirmation once, shows the count, and is undoable for 24 hours.

Someday items are excluded from Today, slipping, all counts, and all notifications. They remain fully searchable and can be pulled back individually.

Definition of Done: amnesty is one action from Today; the count is accurate before commit; undo restores exact prior state including scheduled dates; someday items appear in search but in no count or badge; the threshold is user-configurable.

## Part C6 — Today gate

Hard gate.

- Today renders in under 1.5s cold start on a real Android device
- calendar sync survives a full week without manual intervention — or, if Part C3 was deferred under the Decision 12 calendar stop rule, Today renders correctly without capacity computation and the deferral is recorded
- shutdown ritual completed on at least 5 of 7 days
- **usage: 14 consecutive days meeting the Definition of "used"**
- at least one amnesty sweep performed on real data

Definition of Done: all conditions pass and are recorded. If usage fails twice, apply the Decision 12 stop rule — redesign Today rather than proceeding.

---

# PHASE D — Sync and multi-device

The hardest phase. It comes before the remaining pillars deliberately: sync retrofitted onto seven pillars is far more expensive than onto two.

## Part D1 — Sync relay (Cloudflare Worker + D1)

Deliverable: `edge/` Cloudflare Worker; D1 schema; `wrangler.toml`; `docs/phase_D1_edge.md`.

Minimal surface:

- `POST /sync` — accepts a batch of client ops and a cursor, returns ops the client has not seen
- `POST /pair` — exchanges a one-time pairing code for a long-lived device token
- `GET /calendar/events` — the Phase C3 proxy
- `POST /push/register` — Web Push subscription registration

Storage is Cloudflare D1. Ops rows are stored with their `value` field encrypted client-side; the Worker orders and relays them but never decrypts and never needs the key. This keeps the Worker inside its 10 ms CPU budget and satisfies Decision 8 without the Worker holding any secret capable of reading your data.

Secrets held by the Worker: the Google OAuth refresh token and the VAPID private key, both stored as Wrangler secrets, never in the repository, never sent to a client.

Cost discipline per Decision 11: no cron trigger fires more often than every 15 minutes; `/sync` returns a 304-equivalent empty response cheaply when the client cursor is current; all heavy computation stays on the client.

Definition of Done: deployed to `*.workers.dev` or routed through the Pages domain with automatic HTTPS; no credit card is attached to the Cloudflare account; the D1 schema migrates cleanly via Wrangler; the Worker rejects unauthenticated requests; no secret appears in the repository or in any client bundle; a full day of normal use consumes under 5% of the Workers request quota and under 5% of the D1 daily write quota, measured from the Cloudflare dashboard and recorded in `docs/cost_ledger.md`; the Worker stays within the 10 ms CPU limit under a simulated 500-op sync batch.

## Part D2 — Client sync engine

Deliverable: `src/sync/`, background sync registration.

Implement:

- push local unsynced ops, pull remote ops since the cursor, apply, advance cursor
- apply remote ops with last-writer-wins per field, resolved by HLC with `device_id` as a deterministic tiebreaker
- trigger sync on app focus, on network reconnect, after any mutation with a 5-second debounce, and every 5 minutes while the app is foregrounded — never on a timer while backgrounded
- register a background sync handler in the service worker so queued ops flush after the app is closed
- encrypt each op's `value` client-side before transmission; the key is derived from a passphrase entered at device pairing and never leaves the device

Sync is never blocking. The UI reads local state exclusively and never awaits the network.

The trigger cadence above is chosen to stay far inside the Decision 11 request budget: three devices at this cadence produce roughly 1,000–1,500 requests per day against a 100,000/day allowance. Do not add an unconditional background polling interval — it buys nothing for a single user and is the one change most likely to threaten the free tier.

Definition of Done: two devices converge to identical database state after concurrent offline edits; an op applied twice is idempotent; a device offline for a week catches up correctly on reconnect; the sync status indicator accurately reflects pending, syncing, synced, and error states; no user action anywhere in the app awaits a network response; a 7-day measured request count is recorded in `docs/cost_ledger.md` and is under 5,000 total.

## Part D3 — Device pairing

Deliverable: pairing flow on both surfaces.

The first device becomes the origin and can generate a pairing code. A new device enters the code and receives a device token plus a full op-log replay. Codes expire in 10 minutes and are single-use.

Definition of Done: a second device pairs and reaches identical state within 60 seconds on a normal connection; an expired or reused code is rejected with a clear message; a device can be revoked from any other paired device; revocation takes effect on the revoked device's next sync attempt.

## Part D4 — Sync correctness gate

Hard gate. Conditions fixed before execution.

- an automated three-way convergence test: two simulated devices make concurrent conflicting edits offline, both sync, both converge to identical state — run across at least 200 randomized op interleavings
- deletion is not resurrected by a stale device coming back online after a week
- clock skew of ±1 hour between devices does not cause misordering
- a partial sync interrupted mid-batch leaves the database in a valid state and recovers on retry
- real usage across phone and desktop for 7 days with no manual intervention and no observed divergence

Definition of Done: all conditions pass. Any divergence that is not reproducible triggers the Decision 12 stop rule — add op-log tracing before continuing.

---

# PHASE E — Routines and streaks

## Part E1 — Routine model

Deliverable: routine schema usage, scheduling engine, tests.

Routines live outside the task list entirely — they never appear in the inbox, on Today's top 3, or in slipping. They are a separate surface with their own rhythm.

Support cadences: daily, specific weekdays, N times per week, every N days. Assign each routine to a time block (morning, midday, evening, anytime).

Definition of Done: every cadence type generates correct occurrences across a 90-day window including DST boundaries; routines never appear in task views, asserted by test; completing a routine occurrence is idempotent for a given date.

## Part E2 — Streaks with a forgiveness budget

Deliverable: streak computation and its tests.

A streak survives a configurable number of misses per calendar month (default 2). Alongside the streak, always display the honest metric: days completed this month out of days scheduled.

Pause mode suspends a routine without consuming forgiveness or breaking the streak — for travel, illness, or a deliberate break.

Definition of Done: the forgiveness budget is respected exactly and resets on the first of the month; pause does not consume budget; the monthly completion ratio is displayed alongside every streak; a routine created mid-month computes correctly; no view displays a streak without its accompanying ratio.

## Part E3 — Routines surface

Deliverable: routines route.

Time-of-day blocks rather than a flat checklist. Today shows a compact single-line summary (`morning 2/3`) that links through — routines never expand inline on Today and never compete with the top 3.

Definition of Done: a full day's routines can be checked off in under 15 seconds; the Today summary is one line; all three view states implemented; a paused routine is visibly distinct from a missed one.

---

# PHASE F — Projects and retainers

## Part F1 — Container model

Deliverable: container logic and tests.

Both are containers over the same tasks, differing in shape:

- **Project** — finite. Has a definition of done, exactly one designated next action, and an end state.
- **Retainer** — recurring. Has a monthly cycle, a budget (hours or deliverables), and a template of recurring work that instantiates each cycle.

One `container_fields` table with a `container_kind` discriminator. Do not build two subsystems.

Definition of Done: a task belongs to at most one container; both kinds render in a shared list; converting between kinds preserves tasks and history; a container with no tasks is valid and does not error.

## Part F2 — Retainer cycles and budgets

Deliverable: cycle engine; burn display.

On cycle rollover, instantiate the template's recurring tasks and reset the budget. Display burn as elapsed-versus-consumed: "day 18 of 31, 40% of budget used."

Log out-of-scope work separately — tasks marked as beyond the agreed scope, accumulated per cycle. This is the artifact you want at renewal time.

Definition of Done: rollover fires correctly on the first of the month including across a month with 28 and 31 days; the template instantiates without duplicating if the app is opened multiple times on rollover day; burn is accurate; the previous cycle's record is retained immutably; the scope-creep log is per-cycle and exportable.

## Part F3 — Next action and stall detection

Deliverable: next-action enforcement; stall flagging.

Every active project must designate exactly one next action. A project without one is flagged — this is the single most reliable detector of a dead project.

A container with no activity in 14 days is flagged as stalled and appears in a dedicated review list.

Definition of Done: completing the next action prompts for the next one immediately; a project cannot be marked active without a next action; stall detection is tested across the boundary; stalled containers appear in the Phase H5 weekly review; language avoids guilt framing.

## Part F4 — Container views

Deliverable: project and retainer routes.

Definition of Done: a container shows its tasks, next action, health, and — for retainers — cycle burn; project completion archives cleanly and remains searchable; all three view states implemented.

---

# PHASE G — People and library

## Part G1 — People as a byproduct of capture

Deliverable: person auto-creation; person route.

Typing `@Rahul` in any capture creates or links a person automatically. Free-text observations attach to the person page as dated log lines. There is no separate "add contact" form and no required fields beyond a name.

A person page shows: log lines newest-first, linked tasks, last contact, and next contact due.

Definition of Done: `@name` creates a person on first use and links thereafter; name collisions prompt a disambiguation choice rather than silently merging; a person page renders from links alone with no dedicated data entry ever performed; deleting a person tombstones without orphaning its links.

## Part G2 — Contact cadence

Deliverable: cadence field; surfacing rule.

Optional per person: "check in roughly every N days." When due, the person surfaces as a gentle suggestion on Today — never as an overdue task, never in red, never in a count.

Definition of Done: cadence is optional and defaults to off; due contacts appear in a distinct low-priority zone on Today; logging a contact resets the cadence; a person is never marked overdue.

## Part G3 — Pre-meeting brief

Deliverable: calendar-attendee matching; brief view.

When a calendar event has an attendee matching a known person, surface that person's recent log lines and open items shortly before the event.

Matching is by email first, then by exact name. Ambiguous matches are not guessed.

Definition of Done: matching is tested including the no-match and ambiguous cases; the brief appears within a configurable window before the event; it consumes at most one notification slot per day under the Decision 6 budget; no brief is generated when there is nothing to show.

## Part G4 — Unified library

Deliverable: note kinds; library route.

One note type with a `note_kind` field: journal, highlight, quote, idea. Not four features — one feature with a facet.

Import path for book highlights: a plain clipboard paste that splits on a configurable delimiter, plus a Readwise-format CSV import. No API integration.

A daily journal prompt appears on Today as a single question that rotates.

Definition of Done: all four kinds create, edit, link, and search identically; clipboard import produces one note per highlight with source attribution; the journal prompt rotates deterministically by date; a note links to people and containers through the same `links` table as everything else.

## Part G5 — Resurfacing engine

Deliverable: resurfacing scoring and its tests.

Score candidate notes by: time since last surfaced, term overlap with currently active containers and today's top 3, and explicit user starring. Surface at most one note per day, on Today, dismissible.

Relevance uses FTS5 term overlap — deterministic, offline, and free. No model required.

Definition of Done: scoring is deterministic and unit-tested; the same note does not resurface within a configurable cooldown; dismissal is recorded and reduces future score; a note related to an active project outranks an unrelated older note in a test fixture; resurfacing never consumes a notification slot.

---

# PHASE H — Cross-cutting

## Part H1 — Global search

Deliverable: search route; FTS5 query layer.

One search across every `kind`. Results grouped by kind, ranked by FTS5 relevance with a recency boost.

Definition of Done: results return in under 100ms at 10,000 items, measured; every kind is searchable including someday and archived items; results are keyboard-navigable; the FTS index stays consistent after sync-applied remote ops — asserted by test.

## Part H2 — Command palette

Deliverable: palette component; keybindings.

`Ctrl/Cmd+K` opens a palette that captures, searches, and navigates from one input. Typing plain text captures; a `>` prefix runs commands; anything else searches.

Definition of Done: the palette opens from every route; capture from the palette is identical in behavior and latency to the capture route; commands cover navigation to every top-level view; it is fully operable without a mouse.

## Part H3 — Push notifications

Deliverable: VAPID setup; `SW` push handler; budget enforcement.

Web Push via VAPID, sent from `EDGE` on a cron trigger. VAPID keys are self-generated and self-signed — there is no push service to sign up for and no cost at any volume. Slots, in priority order: evening shutdown, pre-meeting brief, routine block reminder, weekly review.

Use a single cron trigger at a 15-minute cadence that checks whether anything is due, rather than one trigger per notification type. This stays within the free plan's 5-triggers-per-account limit and costs roughly 96 invocations a day against the 100,000 request allowance.

The two-per-day cap from Decision 6 is enforced by a counter checked at the send site. Overflow merges into a digest.

Definition of Done: push arrives on Android with the app closed and on desktop; the cap is enforced in the Worker and tested by attempting a third send; tapping a notification deep-links to the correct route; notifications are individually toggleable; permission denial degrades gracefully with in-app surfacing instead.

## Part H4 — Re-entry screen

Deliverable: re-entry route; absence detection.

On first open after 3+ days away, show what changed rather than what is overdue: routines auto-paused, items that aged into amnesty eligibility, containers that stalled, calendar events coming up, and the single most important thing to do now.

No red. No counts of failure. No streak-break language. One action to resume.

Definition of Done: triggers at the configured absence threshold and not before; language reviewed explicitly against Decision 7 with the review recorded; offers exactly one primary action; dismissible and does not reappear the same day; tested at 3, 7, 30, and 90 days of absence.

## Part H5 — Weekly review

Deliverable: review route.

A guided pass, one screen: completed this week, slipping, stalled containers, retainer burn, routine ratios, people due for contact, inbox zero check.

Definition of Done: completes in under 5 minutes; every section links through to the underlying items; the review is skippable without penalty; the last-reviewed date is recorded and drives the weekly notification slot.

---

# PHASE I — Hardening

## Part I1 — Backup, export, and import

Deliverable: export and import; documented restore procedure.

Export the full database as JSON and as a portable SQLite file. Export notes as a Markdown archive with front-matter. Import restores from either export format.

Backup strategy under the zero-cost constraint, in order of reliance:

1. **Every paired device is a complete replica.** This is the primary backup and it costs nothing. Two devices means two copies; the local-first architecture gives you this for free.
2. **Weekly automatic export to Cloudflare R2** via a cron-triggered Worker, retaining the last 8 snapshots inside the 10 GB free allowance.
3. **Manual export to local disk**, prompted monthly by the Phase H5 weekly review.

Do not rely on D1's built-in point-in-time restore as the primary backup — verify what window the free plan actually provides and record it, but treat it as a convenience rather than a guarantee.

Definition of Done: export produces a file that import restores to a byte-identical materialized state; the Markdown archive opens correctly in a plain text editor and in Obsidian; a full restore from export to an empty device has been performed and recorded; the R2 export job runs on schedule and prunes to 8 snapshots; total R2 usage is recorded in `docs/cost_ledger.md`; the procedure is documented in `docs/restore.md`.

## Part I2 — Performance verification

Deliverable: benchmark suite; recorded results.

Verify every Decision 9 budget against a seeded database of 10,000 items on a real mid-range Android device — not a desktop browser with throttling.

Definition of Done: all four budgets met and recorded with device and date; benchmarks run via a single command; any regression beyond a budget fails `pnpm verify`.

Additionally, close out the cost ledger: record 30 days of measured usage for every row in the Decision 11 table, taken from the Cloudflare and Google Cloud dashboards. Every component must sit under 50% of its free allowance. Any component above 50% is a design problem to fix here, before it becomes a billing problem later.

## Part I3 — Offline and install polish

Deliverable: service worker audit; install experience.

Definition of Done: every route renders offline; airplane-mode capture, triage, and completion all work and sync on reconnect; app update does not lose unsynced ops — tested explicitly; the install prompt is presented at an appropriate moment rather than immediately on first load; a Lighthouse PWA audit passes.

## Part I4 — Accessibility pass

Deliverable: audit against WCAG 2.1 AA; remediation.

Definition of Done: keyboard operation of every flow with no mouse; visible focus throughout; contrast meets AA in both light and dark mode; touch targets at least 44px; screen reader announces capture, triage, and Today coherently; dynamic content changes are announced.

## Part I5 — Recovery drill

Deliverable: `docs/recovery.md` and a completed drill record.

Simulate: total loss of the Cloudflare account, device loss, corrupted local database, a bad migration, and a free tier withdrawn or reduced.

The account-loss drill matters most and is the one that validates the zero-cost architecture: delete the Worker and D1 database entirely, then rebuild from a paired device's local replica and confirm nothing is lost. If that drill passes, no hosting provider has leverage over your data.

Definition of Done: every scenario recovered successfully from the drill; steps documented precisely enough to follow under stress; the account-loss drill was performed against real infrastructure rather than reasoned about; the free-tier-withdrawal scenario names a specific alternative free host and estimates the migration at under one working day.

---

# PHASE J — Optional extensions

Optional. Not prerequisites. Start only after Phase I is complete and the system has been in continuous real use for at least 30 days.

## Part J1 — AI capture parsing fallback

Activate only if the Phase B2 rules demonstrably fail on real captured input — measured, not assumed. Review the actual unparsed-capture log first.

This is the one part of the plan where the zero-cost constraint genuinely bites, because inference is normally metered. Two acceptable routes:

- **Cloudflare Workers AI free daily allocation.** Same account, same Worker, no card. Verify the current free allowance and model list at activation time — this tier changes more often than the rest of the stack. A small instruction-tuned model is more than sufficient for extracting a date and a name from one fragment.
- **A local model in the browser** via WebGPU. Zero marginal cost and nothing leaves the device, at the price of a large download and mediocre Android performance. Viable on desktop, likely not on phone.

If neither route is available within a free allowance at activation time, J1 does not ship. Decision 11 outranks this feature, and Phase B2's rules already cover the overwhelming majority of real capture.

Send only the unparsed fragment. Present the result as an editable suggestion requiring explicit confirmation. Never write directly. Never send surrounding context, linked people, or note bodies.

Definition of Done: the fallback triggers only on rule miss; every suggestion is confirmed before commit; the feature is toggleable off with no functional loss; the privacy boundary in Decision 8 is verified by inspecting outbound payloads; measured usage sits inside the chosen free allowance and is recorded in `docs/cost_ledger.md`; the monthly bill is confirmed at zero after 30 days of use.

## Part J2 — Native Android shell

Activate only if the PWA's share-target and notification reliability prove insufficient in practice.

A Capacitor or TWA wrapper around the existing PWA, adding a true share-sheet target, a home-screen capture widget, and more reliable background notification delivery.

Do not pay for a Play Store developer account. Build a self-signed APK and install it directly on your own device via ADB or a file transfer — this is free, permitted, and sufficient for a single user. A Play listing buys you distribution you do not need. If you later want automatic updates without the store, self-host the APK and check a version endpoint on the existing Worker.

Definition of Done: the wrapper adds no second codebase for application logic; the share target captures from at least three other apps; the widget captures without opening the app; the PWA remains fully functional independently; total spend on this part is zero, with no developer account purchased.

## Part J3 — Two-way calendar

Activate only if time-blocking becomes a genuine practice rather than an aspiration.

Push scheduled tasks as calendar events; reflect edits back. Requires an expanded OAuth scope and a conflict-resolution policy, both of which must be documented here before implementation.

Definition of Done: tasks appear as events and edits round-trip; deleting an event does not delete the task; conflict policy is documented and tested; the expanded scope is recorded as an amendment to Decision 8.

---

# Final stop/go criteria

Proceed past Phase D only if:

- every write path appends to `ops` and the replay test passes
- no autoincrement primary key exists anywhere in the schema
- no code path hard-deletes a user-visible row
- two devices demonstrably converge after concurrent offline edits
- capture latency is within budget on a real device
- the app has survived a genuine multi-week usage period, recorded in the usage log
- no account backing the system has a payment method attached, and `docs/cost_ledger.md` shows every component under 50% of its free allowance

Consider the project successful when it has been used for 60 consecutive days without a gap longer than 3 days, at zero recurring cost — regardless of how many pillars are complete.

If capture and Today are used daily but Phases E–G go untouched, that is a valid and informative outcome. Mark the unused pillars dormant, stop building them, and invest the time in deepening what is actually being opened. A system used daily at 30% scope beats an abandoned system at 100%.
