# Phase C, Part C2 — Top 3 and evening shutdown

Status: **done.**

## What's in place

- `src/routes/TodayRoute.tsx` — Today, now the home route (`/`, replacing
  the placeholder that sat there since Part A4). Exactly three committed
  tasks, prominently, above everything else. If nothing was committed, a
  proposal of three with one tap to accept (`Accept these three`) or swap
  any one of them (`Swap <title>`). Below them, the rest of the day's work
  in a visually secondary list. All three done → a finish line ("That's
  all three. The rest of the day is yours.") and the rest of today folds
  away behind an explicit "Show the rest of today."
- `src/routes/ShutdownRoute.tsx` — the evening shutdown at `/shutdown`:
  review today (what got done, and a checkbox on anything still open that
  was actually finished), then pick tomorrow's three from a preselected
  list, then done. One commit writes tomorrow's three and marks tonight's
  shutdown complete.
- `src/today/proposal.ts` — `rankCandidates(tasks, dayStart)` and
  `proposeTop3()`: the plan's "due today, then slipping, then oldest
  scheduled," as one pure ranking that both routes use.
- `src/today/dayPlan.ts` — `planCommitTop3()`, `planShutdown()`,
  `planSetCompleted()`: pure write plans, each with its exact inverse,
  the same contract as C1's `planScheduleChange()` and B3's
  `planTriageAction()`.
- `src/today/shutdownReminder.ts` + `useShutdownReminder.ts` — the
  notification hook: `EVENING_SHUTDOWN_SLOT`, the reminder-time rule
  (default 20:00, configurable), and the hooks Today uses to surface it.
- `src/today/labels.ts`, `TaskCheck.tsx` — the detail lines under tasks,
  and a native-checkbox task row shared by both routes.
- `src/db/migrations/0002_day_plans.sql` — the `day_plans` table (below).
  `ops.ts` knows its primary key, so `mutate()`, `replayOps()` and B4's
  on-device replay check all cover it.
- `src/routes/taskQueries.ts` gains `DAY_TASKS_SQL`, `DAY_PLANS_SQL`, and
  `LAST_ACTIVITY_SQL`. `DAY_TASKS_SQL` interpolates C1's
  `NOT_DEFERRED_SQL`, and C1's source-scan guard and real-query test now
  cover it too.
- `src/ui/useUndoToast.ts` + `UndoToast.tsx` — B3's undo toast, extracted
  from `TriageView` so Today's "accept" gets the same 10-second undo rather
  than a second copy of the logic.
- `src/scheduling/` gains `localDayKey()` (`'YYYY-MM-DD'`) and
  `moveToDay()` (C1's "keep the time of day" rule, moved out of triage so
  committing to a day shares it).

## `day_plans`: a table of its own, keyed by the date

```text
day_plans(day TEXT PRIMARY KEY,               -- local date, 'YYYY-MM-DD'
          top1_id, top2_id, top3_id,           -- the three slots
          committed_at, committed_via,         -- 'shutdown' | 'proposal'
          shutdown_completed_at,               -- on the evening's own row
          hlc, origin_device)
```

Decision 1 says no new top-level table for a new _pillar_; a new pillar is
a new `kind` plus a side table. A day's plan isn't a pillar or an item: it
isn't searchable, linkable, or something you'd open. It's per-date state
_about_ items, like `links` is. The alternatives were worse:

- **Columns on `task_fields`** (`committed_for`, `commit_rank`) put the
  commitment on the task, but leave nowhere to record that the shutdown
  happened. Part C6's gate needs exactly that ("shutdown ritual completed
  on at least 5 of 7 days"), and Today needs it to know whether to prompt.
- **A new `kind`** means rebuilding `items` to change its `CHECK`
  constraint, for a row type no view would ever list.

The date as the primary key is deliberate, and it's why the key is a
string rather than a UUID. Two devices that each plan Saturday write to the
same row (`'2026-09-12'`), so Phase D's per-field last-writer-wins merges
them rather than creating two Saturdays. Each slot is its own field, so a
conflict resolves slot by slot. See "Notes for later parts."

## The rules, and why each is shaped the way it is

**The proposal: "due today, then slipping, then oldest scheduled."**
`rankCandidates()` buckets open tasks in that order, each task once, under
the first bucket it fits:

1. **Due** by the end of the day, including a deadline that has already
   passed (a missed deadline is still the most time-sensitive thing
   there is). Earliest first.
2. **Carried over** — the plan's "slipping," which Part C4 hasn't defined
   yet. Here it's a task that was rescheduled at least once (C1's
   `touch_count` > 0) or scheduled for an earlier day and not done.
   Ordered the way C4 says slipping is ranked: most-rescheduled first,
   then longest untouched. A task deliberately pushed to a _later_ day
   isn't carried over, however often it was moved, because that move was
   the plan.
3. **Scheduled** for the day. Oldest task first.

Undated tasks that were never moved aren't candidates; nothing says they
belong to today. The shutdown's pick step can still reach them under
"Choose from other open tasks."

**Swapping** replaces a proposed task with the next one in line, and is
disabled when there isn't one. Swaps aren't stored: a proposal is a
suggestion until accepted, never a decision.

**Committing a task to a day moves its `scheduled_for` there**, through
C1's `planScheduleChange()`, keeping its time of day. "Committed for
Saturday" and "scheduled for Saturday" can't disagree that way, and the
C1 rules then do the right thing unprompted. Carrying today's unfinished
task into tomorrow's three is a forward reschedule, so it counts: that's
exactly the signal C4 is built on. Pulling next week's task into tomorrow
is not. Committed tasks also leave the inbox; choosing one for a day is a
triage decision.

**Today includes tasks that haven't been triaged yet.** A capture like
`flight 11am` is on today whether or not it has been through the inbox.
Hiding it until triage would make Today wrong on exactly the days it
matters. Completing one from Today also takes it out of the inbox, or it
would sit there, done, waiting to be triaged.

**The finish state really stops.** All three done shows the finish line.
The rest of today isn't listed underneath, and the button that reveals it
carries no count ("Show the rest of today," not "Show 4 more"). A
finished day announcing how much is left is the opposite of a finish.

**A committed task that stops being eligible** (deleted, moved to someday,
deferred) drops out of its slot. If none are left, Today goes back to
proposing, as if nothing had been committed.

## Three view states, both routes

| State  | Today                                                                                     | Shutdown                                                                           |
| ------ | ----------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| empty  | "Nothing lined up for today…" and one action: Capture something                           | "Nothing to look back on or plan yet…" and one action: Go to Capture               |
| cold   | "Welcome back. No catching up needed." and a fresh three. No carried-over list, no counts | Skips the look back entirely and goes straight to picking; there's no "Back" to it |
| loaded | The committed three (or a proposal), then "Also today"                                    | Review, then pick, then done                                                       |

"Cold" is measured from the newest op (`LAST_ACTIVITY_SQL`), which is the
last time anything was actually done in the app. Reading the newest op by
rowid rather than `MAX(created_at)` keeps it constant-time however long
the ops log grows.

## The notification hook: in-app now, push in Part H3

"Triggered by the day's first notification slot (Decision 6), default 8pm,
configurable." Real push needs the Worker, VAPID keys, and H3's cron
sender, none of which exist yet. So C2 ships the part both halves share:

- `EVENING_SHUTDOWN_SLOT`: the slot's id, its priority (first of
  Decision 6's two), its copy, and its deep link (`/shutdown`). H3's sender
  budgets and sends this.
- `shutdownReminderAt()` / `isShutdownDue()`: from the configured time
  until midnight, unless tonight's shutdown is done. Built from local date
  fields, so 20:00 is 20:00 on a DST day (tested in New York, where the
  gap between two consecutive 8pm reminders across spring-forward is 23
  hours).
- **In-app surfacing today:** from the reminder time on, Today shows an
  "Evening shutdown" card linking to `/shutdown`. It appears at that time
  on its own if the app is already open, and it's gone once tonight's
  shutdown is done ("Tomorrow is planned."). This is also what H3's own
  Definition of Done falls back to when notification permission is denied.
- **The time is configurable** at the bottom of the shutdown page
  (`<input type="time">`). It's stored per device in `localStorage`, like
  the theme, because it's a preference about when _this device_ nudges
  you. When H3 arrives the Worker will need it too, and push registration
  is the natural place to send it.

## Things found along the way

- **Node 26 shadows jsdom's `localStorage`.** Node now ships an
  experimental global `localStorage`: a getter that returns `undefined`
  without `--localstorage-file`. It's the "localStorage is not available"
  warning every test run has printed. App code survived it (every access
  is in a try/catch), but no test could ever observe a stored preference.
  The first reminder-time test failed on it, which is what surfaced it.
  `src/test/setup.ts` now installs an in-memory `Storage` only when the
  real one is unusable, and empties it between tests.
- **Checkboxes lagged behind the tap.** The ticks are controlled by
  database state, so a tap showed nothing until the write and re-query
  came back. Playwright's `check()` failed on it ("clicking the checkbox
  did not change its state"), which is the same lag a phone would show.
  `TaskCheck` now shows the tap immediately. Its first version had an
  A→B→A bug, which its own unit test caught: an override that was merely
  ignored once the database caught up came back when an undo restored the
  old value. It's now dropped for good the moment the database value
  moves.
- **`react-hooks/purity` flags `Date.now()` in named event handlers**
  (though not in inline ones). It can't tell a click handler from render
  code. The write-plan functions now default `now` to the moment they're
  called, as `parse()` already does, and tests always pass it explicitly.
- **The undo toast sat on top of the phone's tab bar.** It's fixed 2rem
  from the bottom, and below 768px the tab bar takes the bottom 3rem. It
  now sits above the bar. This was inherited from B3's triage toast, which
  gets the fix too, since it's the same component now.
- **The shutdown's pick buttons ran their title and detail together** as
  one accessible name. The title is now the name and the detail its
  description (`aria-labelledby` / `aria-describedby`).
- **Two e2e tests were still waiting for the old placeholder heading** on
  `/` (`app.spec.ts`, and the global-shortcut test in `capture.spec.ts`).
  Both now wait for Today's.

## Notes for later parts

- **Part C4** should build its slipping detector on
  `rankCandidates()`'s carried-over rule, or replace that bucket with its
  own and keep the two in one place, so Today's proposal and the slipping
  view never disagree about what "slipping" means.
- **Part C6** counts shutdowns as `day_plans` rows with a non-null
  `shutdown_completed_at`.
- **Phase D:** two devices that commit different threes for the same day
  merge slot by slot, which could mix them (A's first slot, B's second).
  That's always exactly three valid tasks, never a corruption, but D4's
  convergence tests should include it.
- **Shutting down after midnight** plans the day after the new date. At
  00:30 on Saturday it plans Sunday. The pick step always names the day
  it's planning, so this is visible rather than silent. A "day boundary"
  setting (say 4am) is the usual fix, if real usage shows it's needed.
- **Part H3** reads `EVENING_SHUTDOWN_SLOT` and needs the reminder time on
  the Worker side (see above).

## Verification

```bash
pnpm verify      # typecheck + lint + format + 426 unit tests (30 files) + build — green
pnpm test:e2e    # 20 Playwright tests, including e2e/today.spec.ts's 3 — green
```

| DoD requirement                                                                                | Where                                                                                                                                                                                                                                         |
| ---------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| the shutdown flow completes in under 60 seconds                                                | `e2e/today.spec.ts`: review (with a tick-off), pick, commit against the real worker and sqlite-wasm, asserted under 60s. The whole test, database checks included, ran in 1.8s. That's machine speed; human timing on the phone belongs to C6 |
| skipping shutdown produces a sensible proposal rather than an empty screen                     | `proposal.test.ts` (the three sources, their order, DST); `TodayRoute.test.tsx`; `e2e/today.spec.ts` (a carried-over task leads the proposal)                                                                                                 |
| the top 3 persist across reloads and are scoped to a specific date                             | `e2e/today.spec.ts`: accept, reload, same three; clock moved to tomorrow, back to proposing. And shutdown picks appear as tomorrow's three the next morning. `dayPlan.test.ts` on a real database                                             |
| completing all three produces a clear finish state rather than immediately surfacing more work | `TodayRoute.test.tsx`; `e2e/today.spec.ts` (tick all three, finish line shown, rest hidden until asked for)                                                                                                                                   |
| all three view states are implemented                                                          | `TodayRoute.test.tsx` and `ShutdownRoute.test.tsx`: empty, cold, loaded for each (table above)                                                                                                                                                |

Also verified:

- **Upgrade path:** a database already on 0001 with real data takes 0002
  cleanly (`schema.test.ts`). That's what the phone does on its next load.
- **Replay integrity:** a shutdown and its undo replay from the ops log to
  identical tables (`dayPlan.test.ts`). In the real browser, B4's on-device
  check at `/gallery` passes with `day_plans` included (2 live rows, 2
  replayed).
- **In the Browser pane:** Today at 375px in light mode, with the proposal
  in the right order, the shutdown card after 8pm, committed checkboxes
  that survive a reload, and the finish state. The shutdown flow in dark
  mode, with the numbered selection marker in the measured dark ink/paper
  pair and pick-button names as bare titles. No console errors.
