# Phase A, Part A2 — Data model and migration system

Status: **done.**

## What's in place

- `src/db/migrations/0001_init.sql` — the entity spine (Decision 1) and the
  sync-ready primitives it depends on (Decision 2): `items`, `links`,
  `tags`, the five kind-specific side tables, `ops`, and the `items_fts`
  FTS5 index with sync triggers.
- `src/db/schema.sql` — a generated, non-authoritative snapshot of the head
  schema (the concatenation of every applied migration), kept honest by a
  test that fails if it drifts from `src/db/migrations/`.
- `src/db/migrate.ts` — an environment-agnostic migration runner. It knows
  nothing about `node:sqlite` or `@sqlite.org/sqlite-wasm`; it only needs a
  `SqliteConnection` (`exec` + `prepare().all()/.run()`), so the same code
  will drive Part A3's browser worker without changes — only the adapter
  passed in changes.
- `src/db/schema.test.ts` — 32 tests covering every item in this part's
  Definition of Done (list below).

## Deviations from the plan's schema sketch

The plan's Part A2 code block is described as defining the entity spine,
but it's a sketch, not a literal schema — it omits a few columns that its
own Definition of Done, or a later phase, requires. Each of these is
additive (no plan-specified column was removed or renamed) and is recorded
here so the plan text and the real schema don't quietly drift apart, the
same practice used for `docs/phase_A1_toolchain.md`'s deviations.

- **Every kind-specific side table gains `hlc` and `origin_device`.** The
  plan's sketch lists them only on `items`, `links`, `ops`, and `ops`'s
  `device_id`; but this part's own Definition of Done says "every table
  carries `hlc` and `origin_device`." Without them on `task_fields`,
  `routine_fields`, `container_fields`, `person_fields`, and `note_fields`,
  Part D2's per-field last-writer-wins (Decision 2) would have no HLC to
  compare for a side-table field, which breaks conflict resolution for
  exactly the columns most likely to be edited from two devices (a due
  date, a cadence, a budget). `ops` is exempted deliberately, not
  overlooked: every op already carries its own `hlc` and `device_id` by
  construction — the column is literally named `device_id` there because
  an op's origin device is the point of the row, not an incidental
  attribute of it. `schema_migrations` (tooling bookkeeping, not part of
  the entity spine) and the FTS5 shadow tables are exempted for the same
  reason `items_fts` itself is: they hold no user-facing field to
  attribute to a device.
- **`tags` gains `created_at` and `deleted_at`.** The plan's sketch lists
  `tags(item_id, tag, hlc, origin_device)` with no delete marker, but this
  part's own Definition of Done requires "a test asserts that no code path
  issues `DELETE FROM` against `items`, `links`, **or `tags`**." A table
  that must never be hard-deleted from needs somewhere to record a
  removal, so it gets the same tombstone column as `items` and `links`.
  `created_at` was added alongside it for symmetry with `links`, which has
  the same shape (a fact about a relationship, not an entity).
- **`task_fields` gains `defer_until`.** Part A2's own sketch doesn't list
  it, but Part C1 names it explicitly as one of three date concepts that
  "must never be conflated" with `due_at` and `scheduled_for`, on the same
  side table. Adding it now avoids a Phase C migration to bolt a load-
  bearing column onto a table two phases after its shape was supposedly
  fixed.
- **No `FOREIGN KEY` constraints** on `links.from_id`/`to_id`,
  `tags.item_id`, or any `*_fields.item_id` reference to `items.id`. This
  isn't an omission — Part D2 applies remote ops individually as they
  arrive off the wire, and nothing guarantees an item's own creation op is
  applied before every op that references it arrives (a link op racing
  ahead of its target's item op is a normal, not exceptional, outcome of
  per-field sync). Enforced FKs would make that ordinary case a hard sync
  failure. Referential integrity here is a property the write path
  (`mutate()`, Part A3) and the sync engine (Part D2) are responsible for,
  not something the schema enforces at the row level.
- **Indexes** on the columns every subsequent phase's Definition of Done
  already promises a latency budget for: `items.kind`, `items.deleted_at`,
  `links.from_id`/`to_id`, `tags.item_id`, `task_fields.due_at`/
  `scheduled_for`/`someday`, `ops.entity_id`/`synced_at`. None of this is
  called out explicitly in the plan text, but Decision 9's search and
  render budgets are unreachable with full table scans at 10,000 items,
  and adding them now is free — there's no data yet to migrate around.

## Design notes that aren't deviations

- **`schema_migrations` uses a `TEXT` primary key** (the migration id
  string, e.g. `0001_init`), not an autoincrementing integer, to keep the
  "no autoincrement integer primary key exists anywhere" DoD line literally
  true even for tooling metadata that isn't part of the entity spine. It's
  created by `migrate.ts` itself (`CREATE TABLE IF NOT EXISTS`), not as
  migration `0000`, because a migration-tracking table can't itself be
  tracked by the mechanism it bootstraps.
- **`items_fts` is an external-content FTS5 table** (`content='items'`,
  `content_rowid='rowid'`) kept in sync by three triggers
  (`items_ai`/`items_ad`/`items_au`) defined in the same migration, rather
  than left for Part A3's `mutate()` to populate. Part H1's Definition of
  Done requires the FTS index to "stay consistent after sync-applied
  remote ops," which will write through some path other than a hand-
  written `mutate()` call chain (bulk apply during replay) — a trigger on
  `items` itself is the only mechanism guaranteed to fire regardless of
  which code path performs the write.
- **Migration runner is transactional per-migration**: each migration's SQL
  plus its `schema_migrations` bookkeeping insert run inside one
  `BEGIN`/`COMMIT`, rolling back together on any failure. SQLite's DDL is
  transactional, so a migration that creates five tables and fails on the
  sixth statement leaves the database exactly as it was before the
  migration started, not half-applied.
- **Migrations are loaded via `import.meta.glob('./migrations/*.sql', { query: '?raw' })`**,
  not `fs.readFileSync`, specifically so the same `migrate.ts` module works
  unchanged inside a Vite-bundled browser Web Worker in Part A3 — there is
  no filesystem there. The test suite (which runs under Vitest, itself
  Vite-powered) gets this for free.
- **Tests run against `node:sqlite`** (`DatabaseSync`, built into Node 26,
  confirmed to compile FTS5 support with no extra flags — see the FTS5
  test suite), not `better-sqlite3` or any other native addon. This follows
  the precedent `docs/phase_A1_toolchain.md` already set with `jimp` over
  `sharp`: avoid adding a native binding when a built-in or pure-JS option
  covers the need, since native bindings are exactly what broke icon
  generation on this machine. `node:sqlite` is test-only infrastructure —
  the runtime browser path is untouched, still `@sqlite.org/sqlite-wasm`
  per the plan, arriving in Part A3.
- **`node:sqlite`'s types needed a scoped opt-in, not a global one.**
  `tsconfig.app.json` deliberately restricts automatic type inclusion to
  `vite/client` (no ambient `node` globals in browser app code — a
  guardrail worth keeping, since Vite doesn't polyfill `process` and a
  stray `process.env` reference would silently be `undefined` at runtime).
  Rather than widen that project-wide, `schema.test.ts` opts in locally
  with a single `/// <reference types="node" />` directive, which pulls in
  `node:sqlite`'s ambient module declaration for that file only.

## Verification

```bash
node --version   # 26.4.0
npx tsc -p tsconfig.app.json --noEmit   # clean
pnpm verify                              # typecheck + lint + format + test:unit + build — green
```

`pnpm test:unit` runs 32 tests in `src/db/schema.test.ts`, each mapped to a
line in this part's Definition of Done:

| DoD requirement                                                                           | Test(s)                                                                                                |
| ----------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| migrations run cleanly from empty to head                                                 | `migrations: empty to head` (4 tests)                                                                  |
| a fixture database with one row of every `kind` round-trips                               | `fixture round trip: one row of every kind`                                                            |
| FTS5 returns a hit for a body-text query                                                  | `FTS5` (2 tests, including update/delete consistency)                                                  |
| every table carries `hlc` and `origin_device`                                             | `every materialized table carries hlc and origin_device` (9 tests)                                     |
| no autoincrement integer primary key exists anywhere                                      | `no autoincrement integer primary key anywhere` (2 tests, scans every migration file and `schema.sql`) |
| a test asserts that no code path issues `DELETE FROM` against `items`, `links`, or `tags` | `no hard delete against items, links, or tags` — walks every `.ts`/`.tsx`/`.sql` file under `src/`     |

Two tests exist above and beyond the DoD's literal wording, added because
they're the cheapest possible guard against the two failure modes most
likely to bite in Phase D: `schema.sql matches the concatenation of
migrations` (catches silent drift between the generated reference and the
real source of truth) and `replay determinism` (applying the migration set
to two independent fresh databases produces byte-identical
`sqlite_master` — the literal claim Decision 2 makes about `ops` replay,
checked here one level down at the schema level, ahead of Part A3's
`ops`-log version of the same claim).
