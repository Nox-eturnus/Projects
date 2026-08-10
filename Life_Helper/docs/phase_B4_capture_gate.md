# Phase B, Part B4 — Capture gate

Status: **tooling done; the gate itself is not passed yet.**

This part is different in kind from B1–B3. It's a _usage_ gate, not a
build — the plan's own wording: "Hard gate... the app has been installed
to the Android home screen and used from there... usage: 7 consecutive
days... at least 30 real items captured." None of that can be produced by
writing code, and nothing here fabricates it. What this session actually
did:

1. Built the one piece of the gate that genuinely was missing tooling for
   (the ops replay check against _real_ data, not fixtures).
2. Scaffolded `docs/usage_log.md` for the self-reported half of the gate.
3. Left the gate explicitly **not** marked passed, because it isn't —
   see `docs/usage_log.md`'s status table for exactly what's still
   outstanding and how to close it out.

Per the plan's own stop rule for this gate: **do not proceed to Phase C**
until `docs/usage_log.md` shows every condition met.

## What's in place

- `src/db/ops.ts` gained `compareMaterializedTables(live, replayed)`:
  compares every materialized table between two databases, row-order-
  independent (each table is queried `ORDER BY` its own primary key
  before comparing) and column-order-independent (rows are compared via
  a sorted-key representation, not raw object equality). Returns a
  per-table `{liveRowCount, replayedRowCount, matches}` breakdown plus an
  overall `ok`.
- `src/db/worker.ts` gained `verifyReplay()`: reads this device's real
  `ops` log, builds a fresh **in-memory** sqlite-wasm database (`new
sqlite3.oo1.DB({filename: ':memory:'})`, reusing the same `sqlite3`
  module instance `init()` already loaded — no second wasm load), runs
  the same `applyMigrations()` + `replayOps()` used everywhere else
  against it, and compares the result to the live OPFS-backed database.
  The in-memory database is discarded when the call returns; nothing it
  touches is written anywhere, and nothing leaves the device (or even the
  browser tab's own memory) at any point.
- `src/db/client.ts` exposes `dbClient.verifyReplay()`, following the
  exact same leader/follower request-routing pattern as `mutate()`/
  `query()`/`getDeviceId()`.
- `src/routes/GalleryRoute.tsx` gained a "Data integrity" section: a
  button that runs the check and renders the per-table pass/fail
  breakdown plus a one-line verdict. `/gallery` was already a permanent,
  always-shipped reference page (Part A4) with no gating — reusing it
  avoids inventing a new route for what is, longer-term, an occasional
  diagnostic rather than a feature end users need routinely.
- `docs/usage_log.md` — the self-reported tracking file the plan
  requires, with Part B4's five conditions listed against their current
  status, instructions for closing out the remaining ones, and a 7-day
  table ready to fill in.

## Why this belongs in `/gallery` and not a new route

Part I1 ("Backup, export, and import") is where the plan actually builds
general data tooling. This isn't that — it's a narrow, one-off check
tied to one specific gate condition. `/gallery` already exists precisely
as a permanent, low-traffic reference/diagnostic surface outside the
primary nav's feature set (Part A4's own framing: "same idea as
Storybook without the dependency"). Adding one more diagnostic section
there is consistent with what the page already is, rather than a new
surface to maintain.

## Verification

```bash
pnpm verify      # typecheck + lint + format + 270 unit tests (20 files) + build — green
pnpm test:e2e    # 18 Playwright tests, including 2 new dataIntegrity.spec.ts scenarios — green
```

`ops.test.ts` covers `compareMaterializedTables()` itself: a replay that
reproduces the live database exactly (`ok: true`), a deliberately
diverged database (`ok: false`, with the specific table identified), and
row-order-independence (two databases populated in a different write
order still compare equal).

`e2e/dataIntegrity.spec.ts` exercises the real path end to end: capture
two items through the actual UI, triage one and delete the other (real
writes through the real worker, not seeded rows), then run the check
from `/gallery` and confirm every table matches — plus a second test
confirming the empty-device case also passes trivially. This is the
closest an automated test can get to "real captured data, not fixtures";
the actual gate condition still requires running this against a real
multi-day device history, by hand, once one exists.

Two things this test run surfaced, both fixed:

- **A `getByLabel` ambiguity from Part B2.** `page.getByLabel('Capture')`
  started matching two elements once B2 added `<ul aria-label="Parsed
from your capture">` — Playwright's label matching is substring-based
  by default, and "Parsed from your capture" contains "capture". Fixed
  by querying `getByRole('textbox', { name: 'Capture' })` instead, which
  is unambiguous. Worth checking other specs if new `aria-label`s
  containing "capture" get added later.
- **The same PwaPrompts/toast z-index collision Part B3 found, a third
  time.** This time it blocked the "Run ops replay verification" button
  itself, not a time-limited undo. Unlike B3's fix, this isn't given
  another z-index bump — there's no time pressure on this button the way
  there was on a 10-second undo window, so the test simply dismisses the
  PWA prompt first if present, the same thing a real user would
  eventually do once and never see again. Two real occurrences of the
  same root cause (the PWA toast can cover _anything_ positioned at the
  bottom of _any_ page) is worth a shared toast-stacking convention if a
  fourth one shows up — noted here rather than acted on, since neither
  occurrence so far has actually needed one.

## What's still genuinely pending

See `docs/usage_log.md`'s status table. In short: home-screen install,
7 consecutive days of real usage, 30 real items, and running the
integrity check against that real history — none of which a coding
session can produce. Report back once the daily log is filled in (or
sooner, if usage reveals friction worth fixing before day 7 — the plan's
own stop rule).
