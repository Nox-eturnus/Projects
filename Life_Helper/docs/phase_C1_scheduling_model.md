# Phase C, Part C1 — Task scheduling model

Status: **done.**

## What's in place

- `src/scheduling/localDay.ts` — calendar-day arithmetic in the device's
  local timezone: `startOfLocalDay`, `startOfNextLocalDay`,
  `addLocalDays`, `localDayOrdinal`, `compareLocalDays`. Everything goes
  through `Date`'s local fields, never `ms / 86_400_000` (see "Timezones"
  below).
- `src/scheduling/schedule.ts` — the model itself:
  - `planScheduleChange(task, change, now)` — pure, synchronous, the
    single place the rules live. Takes a snapshot of the task's three
    dates plus `touch_count`/`last_touched_at`, and a change in which each
    of `dueAt`/`scheduledFor`/`deferUntil` is independently optional
    (absent = leave alone, `null` = clear). Returns a forward `Write`, its
    exact inverse, and whether the change counted as a touch — the same
    shape as Part B3's `planTriageAction()`, so undo is just "mutate() the
    undo writes," `touch_count` included.
  - `isDeferred(deferUntil, now)` / `deferralCutoff(now)` — visibility.
  - `NOT_DEFERRED_SQL` — the filter fragment every task view's SQL
    interpolates, bound to `deferralCutoff(now)`.
- `src/scheduling/useDeferralCutoff.ts` — the cutoff as a React value
  that's stable all day (so it's a cheap `useQuery()` param) and rolls
  over at local midnight on its own, so a task deferred to tomorrow
  appears at midnight even if the app has been open since before it.
- `src/routes/taskQueries.ts` — `INBOX_SQL` and `RECENT_CAPTURES_SQL`,
  moved out of their route components so the tests can run the real
  queries against `node:sqlite`. Both now filter out deferred tasks;
  `CaptureRoute` now depends on `task_fields` too, since that's where
  `defer_until` lives.
- `src/triage/triageActions.ts` — "schedule for today" and "schedule for
  a date" now delegate their `task_fields` write to
  `planScheduleChange()`, so a triage reschedule counts exactly like any
  other. `TriageItem` extends the model's `TaskSchedule`; the inbox query
  selects the extra columns (with `touch_count` `COALESCE`d to 0, since a
  task with no `task_fields` row would otherwise hand triage a `NULL`).

No schema migration: `task_fields.defer_until` was added in Part A2
precisely so this part wouldn't need one (see
`docs/phase_A2_data_model.md`).

## The rules, and why each one is shaped the way it is

**What counts as a touch.** Decision 4 says `touch_count` goes up "on
every deferral or reschedule"; Part C1 adds that moving `scheduled_for`
forward counts and moving `due_at` doesn't. Filled in precisely:

| Change                                                      | Touch? | Why                                                                                                                                           |
| ----------------------------------------------------------- | ------ | --------------------------------------------------------------------------------------------------------------------------------------------- |
| `scheduled_for` null → a day                                | no     | Planning, not rescheduling. Otherwise every capture parsed with a date, then triaged, would start life already "touched."                     |
| `scheduled_for` → a later local day                         | **+1** | The rule the plan states outright. Includes an overdue task moved to today.                                                                   |
| `scheduled_for` → a later time on the same day              | no     | See "day granularity" below.                                                                                                                  |
| `scheduled_for` → an earlier day                            | no     | Pulling work in is the opposite of avoiding it.                                                                                               |
| `scheduled_for` cleared                                     | **+1** | Otherwise "clear it, set it again next week" is two uncounted moves adding up to one counted one, and Part C4's primary signal leaks.         |
| `defer_until` set, or pushed to a later day, while it hides | **+1** | Deferring is literally Decision 4's "deferral."                                                                                               |
| `defer_until` pulled in, lifted, or set to today/a past day | no     | Nothing becomes more hidden. Re-deferring a task whose old deferral already lapsed counts as a fresh deferral.                                |
| `due_at`, any change                                        | no     | "A deadline change is external, a reschedule is a choice."                                                                                    |
| several of the above in one call                            | **+1** | "Exactly once per move": a move is one user action, however many columns it writes. Tested with scheduled-and-deferred and scheduled-and-due. |

Every counted move also sets `last_touched_at = now`, in the same write.

**Day granularity for `scheduled_for`.** `scheduled_for` is "the day you
intend to do it," but capture stores whatever the parser resolved,
including a time (timed captures like `acne cream 6pm` and `wash face
8pm` make up most of `docs/usage_log.md`). Nudging 3pm to 6pm the same
day isn't the kind of avoidance Part C4 is looking for, and counting it
would make that frequent, harmless edit inflate the slipping signal. So the stored value
keeps its time; the touch rule compares local calendar days.

**`defer_until` is a date.** "Hidden from all views before this date."
`planScheduleChange()` normalizes it to the first instant of its local day
before writing, and the visibility rule is day-granular either way: a
task is visible from the first instant of its defer day. A value carrying
a time of day (a synced or imported row, say) still reappears at the start
of its day, not at that time. This is also what makes the query parameter
stable: `deferralCutoff(now)` is "the start of tomorrow," which only
changes at midnight, so views don't re-query on every render.

**The three dates stay independent.** Nothing reconciles them — a task
can be scheduled for Monday and deferred until Wednesday, and Monday's
Today view (Part C2) simply won't show it. Reconciling them would be
exactly the conflation Part C1 rules out.

## "Absent from every view" — enforced three ways

1. **The real queries against a real database.** `schedule.test.ts` seeds
   a `node:sqlite` database through `mutate()` with a visible task, one
   deferred to tomorrow, one whose deferral lapsed yesterday, one deferred
   to today, and one with no `task_fields` row at all, then runs every
   query in `taskQueries.ts`: the deferred task is absent one millisecond
   before its day and present from its first instant.
2. **A source scan for views that don't exist yet.** Like
   `schema.test.ts`'s `DELETE FROM` guard, it finds every SQL template
   literal under `src/` that selects `kind = 'task'` and fails if one
   doesn't interpolate `NOT_DEFERRED_SQL`. Today and slipping (Parts C2
   and C4) inherit the rule by failing the build if they forget it. It also asserts it found at least the two views that exist today,
   so it can't pass vacuously. Its limit, stated in the test: it covers
   queries written the way this codebase writes them, not every possible
   spelling.
3. **In a real browser, across midnight.** `e2e/scheduling.spec.ts` seeds
   a deferred-to-tomorrow task through the real sqlite-wasm worker, pins
   the page clock to 23:59, confirms the task is absent from both Capture's
   recent list and the Inbox, then advances the clock one minute and
   confirms it appears — no reload, no unrelated write to jog the query.

Both the SQL filter and the source scan were mutation-checked: deleting
the filter from `RECENT_CAPTURES_SQL` fails both the query test and the
scan.

## Timezones

The device is in IST (UTC+05:30, no DST), but a timezone-naive day
calculation is wrong here even without DST: 03:00 and 07:00 on the same
IST day fall on different UTC days, so `Math.floor(ms / 86_400_000)`
would call a 3am → 7am nudge a reschedule. `localDay.ts` avoids both that
and the DST class of bug by only ever reading local `Date` fields.

The tests run real transitions, not a mocked `Date`: `src/test/timeZone.ts`
sets `process.env.TZ` for the duration of a synchronous callback (Node
re-reads it at runtime). Zones and dates covered:

- **America/New_York** — spring forward (Sun 8 Mar 2026, a 23-hour day)
  and fall back (Sun 1 Nov 2026, a 25-hour day): day lengths, `addLocalDays`
  keeping 9am at 9am over 23 and 25 elapsed hours, 22 hours apart on the
  short day being the same day, 40 minutes apart across midnight being
  different days, 24 hours apart on the long day still being the same day,
  a deferral reappearing at midnight 23 hours after the previous one, and
  the midnight-rollover hook firing correctly on both sides of the
  transition.
- **Europe/London** — spring forward (Sun 29 Mar 2026).
- **America/Sao_Paulo, 4 Nov 2018** — DST began _at_ midnight, so 00:00
  didn't exist that day; the start of that day is its 01:00, and a task
  deferred to it reappears then.
- **Asia/Kolkata** — the half-hour offset case above.

Mutation-checked, not just passing: swapping `localDayOrdinal` for
epoch-day division fails 10 tests, and swapping `startOfNextLocalDay` for
"start of day + 24h" fails 6.

**Restoring the zone afterwards needed care.** `delete process.env.TZ`
does _not_ put Node back on the machine's zone — it keeps the last one it
was given — and `TZ=''` means UTC. `withTimeZone()` resolves the current
zone's IANA name first and restores that, which is correct whether or not
`TZ` was set to begin with. Found by checking, before relying on it.

## Notes for later parts

- **Part D2: `touch_count` under last-writer-wins.** Two devices that each
  reschedule the same task offline both write `touch_count = n + 1`, and
  per-field LWW converges on `n + 1`, not `n + 2`. For a slipping
  heuristic that's an acceptable undercount, but it's a real property of
  storing a counter as an LWW field, and D2 is where to decide whether it
  matters (a count derived from the ops log wouldn't have it).
- **Part C5: "untouched" needs its own definition.** `last_touched_at` is
  stamped only by counted moves, as Decision 4 describes it. A task that's
  been pulled into today, or edited, hasn't been "touched" in this sense.
  C5's amnesty eligibility shouldn't read `last_touched_at` alone as "last
  interacted with."
- **No UI sets `due_at` or `defer_until` yet.** This part's deliverable is
  the model and its tests; the surfaces that set those fields (Today's
  swap, slipping's actions) arrive with the parts that need them, and
  should call `planScheduleChange()` rather than writing `task_fields`
  directly.

## Verification

```bash
pnpm verify      # typecheck + lint + format + 337 unit tests (23 files) + build — green
pnpm test:e2e    # 17 Playwright tests, including e2e/scheduling.spec.ts — green
```

| DoD requirement                                            | Where                                                                                                                                                                                                  |
| ---------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| the three fields are independently settable and tested     | `schedule.test.ts` — "the three dates are independently settable" (each alone, all together, absent vs `null`, no-op, invalid input)                                                                   |
| rescheduling increments touch count exactly once per move  | `schedule.test.ts` — the two `touch_count` suites (pure), and "through mutate() on a real database" (six moves → three counted, exactly three `touch_count` ops, undo exact, ops replay still matches) |
| deferred items are absent from every view until their date | `schedule.test.ts` — real queries on `node:sqlite` plus the source-scan guard; `e2e/scheduling.spec.ts` in a real browser across midnight                                                              |
| timezone handling is tested across a DST boundary          | `localDay.test.ts`, the DST suite in `schedule.test.ts`, and `useDeferralCutoff.test.tsx` — New York, London, São Paulo, Kolkata                                                                       |
