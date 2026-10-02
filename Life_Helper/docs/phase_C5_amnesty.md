# Phase C, Part C5 — Amnesty and decay

Status: **done.** Amnesty is called **Fresh start** where the user sees
it. "Amnesty" pardons a wrongdoing, and nothing here was one
(Decision 7). The someday tier is **Someday**, at `/someday`.

## What's in place

- `src/db/migrations/0003_amnesty.sql`:
  - a new `amnesty_sweeps` table: one row per sweep, with when it ran,
    the threshold, how many tasks it moved, and `undone_at`;
  - a new `task_fields.amnesty_sweep_id` column, which tags each task a
    sweep moved.

  `schema.sql` is regenerated, and `ops.ts` registers the table so
  mutate, replay and the replay check all cover it.

- `src/amnesty/amnesty.ts` — the logic, as pure planners with exact
  inverse writes:
  - `planSweep()` and `planUndoSweep()`;
  - `planBringBack()`;
  - `canUndoSweep()` and `undoDeadline()`;
  - `untouchedBefore()`;
  - `toFtsQuery()`;
  - the threshold setting.
- Queries in `taskQueries.ts`:
  - `AMNESTY_ELIGIBLE_SQL` decides which tasks a sweep would move.
  - `SOMEDAY_SQL` lists Someday tasks, with optional FTS5 search.
  - `LATEST_SWEEP_SQL` finds the newest sweep that can still be undone.
  - `SWEPT_ITEMS_SQL` finds the tasks a sweep's undo restores.
  - The inbox queries now exclude someday too (see below).
- `src/amnesty/FreshStart.tsx` — the control on Today: an offer, then a
  confirmation with the count, then the 24-hour undo.
- `src/routes/SomedayRoute.tsx` (`/someday`) — the Someday list. It's
  searchable, and each task can be brought back to today or the inbox.
  It's linked from Today's footer, the Fresh start note, and Settings.
- Settings → **Fresh start** — the threshold, in whole days from 7 to 365
  (default 30).

## The rules, and why each is shaped the way it is

**"Untouched" means no change of any kind, read from the ops log.** A
task's last touch is its newest op: any change to the item or its task
fields, since both share its id as `entity_id`. If it has none, its
creation time is used.

- C1's `last_touched_at` isn't enough. It moves only on a reschedule or
  deferral, so a task that was renamed, triaged or re-estimated yesterday
  would look untouched.
- The ops log is Decision 2's source of truth, and is already indexed on
  `entity_id`.

**The sweep's own writes don't count as a touch.** Ops on `someday` and
`amnesty_sweep_id` are left out. Otherwise undoing a sweep would leave
every task looking freshly touched, rather than "exactly as before."
With them left out, an undone sweep leaves every task exactly as
eligible as it was, and the offer comes back. A test checks this.

**What's eligible.** An open task, not already someday, archived,
deferred or deleted, untouched since before the threshold. It must also
have **nothing still ahead of it**:

- **No date today or later.** A task planned for next month was set up
  on purpose, and age alone doesn't make it abandoned.
- **No deadline today or later.** For a real deadline, moving it out of
  sight would be harmful.
- **Past dates don't protect a task.** A task planned for 45 days ago and
  left alone is exactly what amnesty is for.

**Day-granular threshold.** "Untouched before the start of the day N days
ago", so the eligible set doesn't shift minute to minute while the
confirmation is open.

**The count is accurate before commit.** The confirmation snapshots the
eligible rows when it opens, shows their count, and the sweep writes
exactly those rows. If something changes underneath while the sheet is
open, the count still describes what will actually happen.

**A sweep changes two fields per task, nothing else:** `someday = 1` and
`amnesty_sweep_id`. Status, dates, touch count and title stay as they
were. An inbox task keeps `status = 'inbox'`, which is why `INBOX_SQL`
and `RECENT_CAPTURES_SQL` now filter someday too. (Triage's own "someday"
had always set `status = 'active'`, so the inbox had never needed the
filter before.)

**Undo for 24 hours** works from two places:

- Today's 10-second toast, immediately after the sweep.
- A note on Today for the next 24 hours ("You can undo it until …"),
  which survives reloads because the sweep is a database row.

Undo restores only the tasks still tagged with that sweep and still in
someday:

- A task brought back by hand in the meantime is untagged, so it's left
  alone.
- A task set aside again by other means isn't pulled out by mistake.
- The sweep is marked `undone_at`, so its undo isn't offered twice.

Exact prior state, dates included, is checked by comparing every task's
business columns before the sweep and after its undo.

**Bringing one back** (the plan's "pulled back individually"):

- **To today:** scheduled for today, keeping its time of day, through
  C1's `planScheduleChange()`, so a move from an earlier day counts like
  any other. The task becomes active.
- **To the inbox:** back for triage, with its dates left alone.

Either way it's untagged from its sweep, and `updated_at` is stamped.
Bringing a task back is working on it, so its decay clock restarts
instead of making it eligible for the next sweep straight away. Each is
undoable from the toast.

**Someday items appear in search, but in no count or badge.**

- `SOMEDAY_SQL` is the only query that lists them.
- Today, Revisit, the shutdown, the inbox (and triage's "N items left"),
  recent captures and the eligibility query all exclude them. A test
  checks each one.
- Nothing shows how many tasks are in Someday — not the nav, not Today,
  not the Fresh start note after a sweep, not the Someday page.
- The one count in the whole feature is the confirmation's, which the
  plan requires.

**Search** turns what's typed into quoted prefix terms that must all
match (`"sour"*`). Quotes are stripped, so nothing typed can be read as
FTS5 syntax. A test throws operators, parentheses and column filters at
it. A search with no hits says so, and doesn't show the empty state.

**The threshold is per device**, in localStorage, like waking hours and
the reminder time. It's a preference about what to offer, not data.

## "Decay job"

The plan lists a decay job. There's no scheduled job, by design. A task
becomes eligible the moment it crosses the threshold, and eligibility is
a query: `useQuery` re-runs it whenever the data changes, and its
parameters move with the deferral cutoff at midnight. That means:

- there's no background timer, the same rule as C3's calendar refresh;
- there's nothing to fall behind while the app is closed;
- there's no server involved, which matters for an offline-first app
  whose only cron (Part H3) lives on the Worker.

Decay never acts on its own. Decision 4 says items become _eligible_,
and only the user's one tap moves them.

## Three states (Decision 7)

| View                | empty                                                                                     | cold                                                                                    | loaded                                                                       |
| ------------------- | ----------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| Someday             | "Nothing in Someday. Tasks you set aside … wait here, kept and searchable…" → Go to Today | "Welcome back. Everything here is set aside on purpose — bring back whatever you want…" | "Set aside, not gone. Out of Today and every list until you bring one back." |
| Fresh start (Today) | renders nothing                                                                           | the same quiet offer; Today's own cold state is unchanged                               | the offer, or the 24-hour undo note                                          |

## Language review against Decision 7

| Text                                                                                                                                                          | Review                                                                                          |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| "Fresh start" (not "Amnesty")                                                                                                                                 | No pardon, no wrongdoing                                                                        |
| "Tasks untouched for 30 days or more can move to Someday — kept and searchable, just out of the way."                                                         | Neutral, factual, an option rather than a demand. No count on Today                             |
| "Move 3 tasks untouched for 30 days or more to Someday?" / "They're kept and searchable, and you can bring any of them back. You can undo this for 24 hours." | The plan's required count; reassures that nothing is lost. Never asks for a reason (Decision 4) |
| "Fresh start moved some older tasks to Someday. You can undo it until …"                                                                                      | "Some", not a count                                                                             |
| "Set aside, not gone." / "Everything here is set aside on purpose"                                                                                            | Someday is a real place, not a graveyard                                                        |
| "Brought back to today" / "Brought back to the inbox"                                                                                                         | Plain confirmations                                                                             |

The words "overdue", "late", "behind", "fail", "missed", "neglect",
"abandon" and "forgot" appear nowhere. `SomedayRoute.test.tsx` checks
every state's text against them and against any "N tasks" count.

## Verification

```bash
pnpm verify      # typecheck + lint + format + unit tests + build
pnpm test:e2e    # Playwright, including e2e/amnesty.spec.ts
```

| DoD requirement                                           | Where                                                                                                                                                                                                                |
| --------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| amnesty is one action from Today                          | `TodayRoute.test.tsx` (including when Today itself is empty); `e2e/amnesty.spec.ts`                                                                                                                                  |
| the count is accurate before commit                       | `amnesty.test.ts` ("the count shown is exactly what is moved, and nothing else changes", on a real database); `FreshStart.test.tsx`; `e2e/amnesty.spec.ts` ("Move 2 tasks…", then exactly those two leave Today)     |
| undo restores exact prior state including scheduled dates | `amnesty.test.ts` (every business column of every task, before vs. after undo, with eligibility identical and an ops-log replay); 24-hour window tested at its boundary; `e2e/amnesty.spec.ts` (undo after a reload) |
| someday items appear in search but in no count or badge   | `amnesty.test.ts` (FTS search; absent from Today's, Revisit's, the inbox's and recent captures' queries, and from eligibility); `SomedayRoute.test.tsx` (no counts); `e2e/amnesty.spec.ts` (search)                  |
| the threshold is user-configurable                        | Settings → Fresh start; `SettingsRoute.test.tsx`; `amnesty.test.ts` (a shorter threshold reaches newer tasks); `FreshStart.test.tsx` (the offer uses the stored threshold)                                           |

## Notes for later parts

- **Part C6** ("at least one amnesty sweep performed on real data"):
  count `amnesty_sweeps` rows with `undone_at IS NULL`.
- **Part H1 (global search)** must include someday and archived tasks
  (its own DoD says so). `SOMEDAY_SQL`'s FTS clause and `toFtsQuery()`
  are the pattern.
- **Part H3 (notifications)** must exclude someday tasks from every
  trigger.
- **Part H4 (re-entry)** shows "items that aged into amnesty
  eligibility". That's `AMNESTY_ELIGIBLE_SQL`, and its Fresh start offer
  is the action.
- **Phase D:** `amnesty_sweeps` syncs like any table, so a sweep on the
  phone can be undone from the laptop within the 24 hours.
