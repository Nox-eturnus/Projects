# Phase A, Part A3 — Local database layer and reactive query API

Status: **done.**

## What's in place

- `src/db/hlc.ts` — pure Hybrid Logical Clock logic (tick/format/parse/compare), persisted through an injected `HlcStore` so it's testable without OPFS.
- `src/db/ops.ts` — `mutate()`, the single write entry point, and `replayOps()`, its inverse. Both operate over the generic `SqliteConnection` interface from `migrate.ts` (Part A2), so they're unit-tested against `node:sqlite` and driven by `@sqlite.org/sqlite-wasm` in the worker with no changes.
- `src/db/worker.ts` — the dedicated Worker that owns the only open OPFS-backed SQLite connection. Installs the `opfs-sahpool` VFS, runs Part A2's migrations, and exposes `mutate`/`query`/`getDeviceId`/`onChange` over Comlink.
- `src/db/client.ts` — main-thread API. Implements leader election across tabs (Web Locks) and a request relay for non-leader tabs (BroadcastChannel) — see "Why not a SharedWorker" below for why this exists at all.
- `src/db/useQuery.ts` — React hook that re-runs a query when a mutate() call touches a declared dependent table, in this tab or another.
- `src/db/debugHarness.ts` + `debug-db.html` — a raw read/write test harness, built only when `LIFE_HELPER_INCLUDE_DEBUG_HARNESS=1` (see "Debug harness" below). Never ships in the real deploy.
- `e2e/db.spec.ts` — Playwright tests for every guarantee that can't be exercised outside a real browser: persistence across a reload, persistence across a full browser process restart against a real on-disk profile, two tabs sharing one database without corruption, and leader failover.
- `src/db/hlc.test.ts`, `src/db/ops.test.ts` — Vitest unit tests against `node:sqlite`, same pattern as Part A2's `schema.test.ts`.

## Why not a SharedWorker

The plan doesn't prescribe a specific worker topology, only "a Web Worker with the OPFS VFS." A SharedWorker looked like the obvious choice for the multi-tab requirement — one instance per origin, shared by every tab automatically — and was the first thing tried.

It doesn't work in this project's actual test environment. Probing directly (see the session that built this part): `navigator.storage.getDirectory()` succeeds inside a SharedWorker here, but `FileSystemFileHandle.prototype.createSyncAccessHandle` — the specific API `opfs-sahpool` needs — is missing, while the identical check inside a plain dedicated Worker succeeds. This reproduced consistently. Real Chrome on Android is expected to support this fully, but the gap was real, reproducible, and enough to disqualify building the whole persistence layer on top of an API that isn't reliably present across the Chromium family this project actually has to run in.

The SQLite Wasm project's own docs independently confirm the harder constraint underneath this: `opfs-sahpool` "does not support multi-tab concurrency" at all — it pre-allocates and locks every file handle in its pool, so two independent Worker instances can't open the same OPFS-backed database concurrently regardless of which worker type hosts them. A SharedWorker would only have removed the need to coordinate _which_ tab owns the connection; it was never going to remove the need for exactly one connection to exist.

So the architecture is: a plain dedicated Worker, owned by exactly one tab at a time (**client.ts**'s "leader"), with every other tab relaying through it. This needed building regardless of worker type, and it's more portable than a SharedWorker-based design would have been anyway (Safari has never implemented SharedWorker; Web Locks and BroadcastChannel — what this relies on instead — both have full Baseline support).

## Leader election and cross-tab relay

- **Web Locks API** (`navigator.locks`) decides leadership. The first tab to acquire `life-helper-db-writer` (via `{ifAvailable: true}`, so it doesn't queue) creates the Worker. Every other tab sees the lock is held, becomes a follower, and issues its own non-`ifAvailable` request that sits in the queue — when the leader tab closes, the browser releases its lock automatically and the queued request resolves, promoting exactly one follower.
- **BroadcastChannel** (`life-helper-db`) relays `mutate`/`query`/`getDeviceId` calls from followers to the leader, and broadcasts `{type: 'change', tables}` from the leader to every tab (including itself, via a direct local call, since BroadcastChannel never delivers a message back to the sender) so `useQuery()` stays reactive across tabs, not just within one.
- **A genuine race, found by the e2e suite, not reasoned about in advance**: a follower that sends a request right as it's being promoted to leader would never get a reply. Its own request goes out over BroadcastChannel, which by spec never delivers a message back to the tab that sent it — and if that same tab becomes the leader before any other tab answers, nothing ever will. `e2e/db.spec.ts`'s failover test reproduced this reliably (timing out every run, not flaky) once a leader tab closed while a request from the about-to-be-promoted tab was in flight. Fixed in `setUpAsLeader()`: any request still in `this.pending` at the moment this tab becomes leader is served directly against the local worker instead of waiting on a channel reply that can't arrive. `docs/phase_A1_toolchain.md` and `phase_A2_data_model.md` both note deviations found by _reasoning_ about the plan's gaps; this one is different in kind — it was only found because the e2e test exercised the real timing, which is the whole reason this part has browser-level tests at all rather than stopping at the unit-testable subset.
- **A second, library-level race**, also only visible under real timing: `opfs-sahpool` pre-allocates its file handles and "does not support client-transparent concurrency" per its own docs. A newly-promoted tab calling `installOpfsSAHPoolVfs()` within milliseconds of the previous leader's tab closing isn't guaranteed the browser has finished releasing that tab's handles yet. `worker.ts` wraps this specific call in a retry (8 attempts, 250ms apart — comfortably inside `client.ts`'s 10s relay timeout) rather than depending on cleanup timing that isn't contractually instant.

## device_id and HLC storage

Both live in a `_local_state` table (`key TEXT PRIMARY KEY, value TEXT NOT NULL`) inside the same SQLite database file, created by `worker.ts` directly rather than as a numbered migration — like `schema_migrations` (Part A2), it's tooling/runtime bookkeeping, not part of the entity spine.

The plan's wording is "device_id generated once and persisted in OPFS." Since the database file itself is the thing durably persisted in OPFS (via the `opfs-sahpool` VFS), storing `device_id` and the HLC state as rows in that same file satisfies this without a second, independent OPFS file to manage — one less thing that can desync from the data it's describing, and one less thing Part A3 has to prove survives a restart, since the reload/restart e2e tests already prove the database file does.

## mutate() and ops-log design

- **One `ops` row per changed field, computed by diffing against the current row** — an update that sets a field to its existing value produces zero rows and doesn't touch the row's `hlc`/`origin_device` bookkeeping either. A `mutate()` call creating a brand-new row with zero non-key fields (legal for tables like `task_fields`, where every column has a `DEFAULT`) still logs exactly one synthetic `__row__` marker op, or `replayOps()` would never learn that row exists at all from the ops log alone — this was a real gap found while writing the test for it, not a hypothetical.
- **The HLC ticks once per `Write`, not once per `mutate()` call and not once per field.** A single `mutate()` call can touch several rows at once (e.g. creating an `items` row and its `task_fields` row together, which Decision 3's "capture never blocks" requires to be one atomic write) — those need distinguishable timestamps for Part D2's per-field LWW to make sense of them as separate events. Every field-op belonging to the same `Write` shares that one hlc value, which is exactly what lets `replayOps()` regroup a flat stream of per-field ops back into the atomic per-row writes that produced them: it groups by `(entity_table, entity_id, hlc)`, and that grouping is exact, not heuristic, because of this rule.
- **No `FOREIGN KEY` constraints, and no requirement that a row's primary key appear in its own `fields`.** `entity_id` is computed from `Write.key` (joined with a `�` separator, not a printable character — `tags.tag` is free text and could otherwise collide with one) and is fully sufficient on its own to reconstruct which row a group of ops belongs to during replay; primary-key values never need to be logged as ops in their own right.
- **`applyToMaterializedTable()` is the single function that turns a `{table, key, fields, hlc, deviceId}` write into an `INSERT`/`UPDATE`**, shared unchanged between `mutate()`'s live path and `replayOps()`'s reconstruction path. This is what makes the replay-determinism claim (Decision 2) something the code structurally can't violate by accident, rather than something that merely happens to hold today.

## RPC: Comlink, not hand-rolled

The plan offers either. Comlink was chosen because the two things a hand-rolled protocol would need to get right — request/response correlation across `postMessage`, and error propagation that preserves something usable on the other side — are exactly what a small, well-tested library exists for, and the added dependency is tiny (4.4.2, MIT, zero further dependencies). `worker.ts` exposes a plain class instance; `client.ts` gets `Comlink.Remote<WorkerApiImpl>` for free from that, so the Promise-wrapping of every method is inferred rather than hand-typed.

## Debug harness

`src/db/debugHarness.ts` and `debug-db.html` expose `dbClient` on `window` with no auth of any kind, for Playwright and manual driving. Vite only includes `debug-db.html` in the build when `LIFE_HELPER_INCLUDE_DEBUG_HARNESS=1` (`vite.config.ts`); `playwright.config.ts`'s `webServer` sets it (via `cross-env`, added as a devDependency for Windows compatibility — bare `VAR=1 cmd` doesn't work outside a POSIX shell). The real Cloudflare Pages deploy runs a plain `pnpm build`, which never sets this, so the harness never reaches production. Confirmed directly: a plain `pnpm build` produces a `dist/` with no `debug-db.html` in it at all.

## Deviations from `tsconfig.app.json`'s isolation

Two files needed a scoped types opt-in rather than a project-wide one, continuing the pattern Part A2 set with `schema.test.ts`'s `node:sqlite` reference:

- `src/db/migrate.ts` gained `/// <reference types="vite/client" />`. It's reached from `tsconfig.e2e.json` (via `db.spec.ts` → `ops.ts` → `migrate.ts`), which — unlike `tsconfig.app.json` — doesn't list `vite/client` in its `types` array, so `import.meta.glob` didn't resolve there without it.
- Every relative import under `src/db/` now uses an explicit `.js` extension (e.g. `from './migrate.js'`). `tsconfig.e2e.json` uses `moduleResolution: nodenext`, which requires this; `tsconfig.app.json`'s bundler-mode resolution accepts it too, so one spelling works under both projects.

`worker.ts`'s `SqliteWasmConnection` class also couldn't use TypeScript's constructor-parameter-property shorthand (`constructor(private readonly db: Oo1Db) {}`) — `erasableSyntaxOnly` rejects it, since it's not just an erasable type annotation but syntax that changes what code gets emitted. Written as an explicit field assignment instead.

## Verification

```bash
pnpm verify      # typecheck + lint + format + 62 unit tests (4 files) + build — green
pnpm test:e2e    # 6 Playwright tests, including all 4 db.spec.ts scenarios below — green
```

Every line of this part's Definition of Done, and where it's proven:

| DoD requirement                                                          | Where                                                                                                                                                                                                                               |
| ------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| data survives a hard browser restart                                     | `e2e/db.spec.ts`: reload test                                                                                                                                                                                                       |
| data survives an OS restart                                              | `e2e/db.spec.ts`: real `chromium.launchPersistentContext` relaunch against the same on-disk profile — `storageState()` doesn't capture OPFS, so this couldn't be shortcut through the normal context fixtures                       |
| every write produces exactly one `ops` row per changed field             | `src/db/ops.test.ts`                                                                                                                                                                                                                |
| replaying ops from empty reproduces materialized tables byte-identically | `src/db/ops.test.ts`                                                                                                                                                                                                                |
| the HLC never goes backwards across a reload                             | `src/db/hlc.test.ts`, at the pure-logic level; the persistence mechanism it relies on (survives a reload) is the same one the OPFS e2e tests already prove for the whole database file, since HLC state lives in a row in that file |
| concurrent writes from two tabs do not corrupt the database              | `e2e/db.spec.ts`: two-tab test (shared state, cross-tab reactivity) and failover test (leader closing mid-session)                                                                                                                  |

All manually verified end-to-end first, in a real browser via the Claude Code Browser pane, before being written up as the automated Playwright suite above — the SharedWorker gap, the `opfs-sahpool` handle-timing race, and the self-broadcast-exclusion race were all found this way, not predicted from documentation alone.
