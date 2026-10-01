# Phase C, Part C4 — Slipping view

Status: **done.** The view is called **Revisit** where the user sees it
(nav, page title, URL `/revisit`); "slipping" stays the internal term, in
code and here, so it can be traced back to the plan.

## What's in place

- `src/slipping/slipping.ts` — the detection logic. `isSlipping()`,
  `compareSlipping()`, `findSlipping()`. **One definition, shared with
  Today:** Part C2's proposal already had a "carried over" bucket standing
  in for slipping; it now calls `findSlipping()` instead of keeping its own
  copy of the rule, as C2's notes asked. A test asserts the two produce the
  same tasks in the same order.
- `src/slipping/slippingActions.ts` — the three actions, as pure planners
  that return forward writes plus their exact undo (the same contract as
  `planTriageAction()` and `planCommitTop3()`): `planDoItNow()`,
  `planScheduleForToday()`, `planBreakDown()`, `planLetGo()`.
- `src/routes/RevisitRoute.tsx` (`/revisit`, now in the nav) — the view,
  its three states, and a sheet for each action that needs a choice.
- `SLIPPING_SQL` in `taskQueries.ts` — Today's rows plus the project a task
  is filed under. It's in the deferral test that covers every task view.
- `NOT_ARCHIVED_SQL` — archived tasks (see "break it down") are excluded
  from `DAY_TASKS_SQL` (Today and the shutdown) and `SLIPPING_SQL`. The
  inbox queries already list only `status = 'inbox'`.
- `describeSlipping()` in `labels.ts` — the detail line under each task.

## The rules, and why each is shaped the way it is

**What's slipping.** An open task, not planned for a later day, that was
either moved at least once (C1's `touch_count` > 0) or scheduled for an
earlier day that has passed. This is exactly C2's carried-over rule,
which was written to match the plan's C4 wording. A task deliberately
moved to a later day isn't slipping, however often it was moved: that
move was the plan. An undated task that was never moved isn't either —
nothing says it was meant for any day. Long-untouched undated tasks are
C5's job (amnesty), not this view's.

**Ranking: touch count first, age second.** Most-moved first. Among
equals, the one left alone longest: age is time since `last_touched_at`,
or since `created_at` if it was never touched. So "a task deferred four
times" outranks "a task that has sat untouched for twelve days," as the
plan asks, and two equally-moved tasks are ordered by how long they've
been left. Full ties fall back to creation time, then id, so the order
is total and stable.

**Today's committed three are left out.** They're already what "do it
now" would make them.

**Do it now** adds the task to today's top 3 through C2's
`planCommitTop3()`:

- A free slot (fewer than three committed) takes it at the end.
- Three committed, at least one still open: a sheet asks which open one
  it replaces. The replaced task stays scheduled for today; it just isn't
  one of the three. A finished task is never offered for replacing — its
  slot records what got done.
- All three already done: there's nothing worth replacing, so the task
  joins the rest of today (`planScheduleForToday()`), without touching the
  three.
- No plan for today yet: it's committed on its own. Committing the two
  proposed tasks alongside it would move other tasks' dates (and possibly
  their touch counts) as a side effect of a click on a different task.
  Today then shows it under "Your three" as one of up to three, the same
  as a shutdown that picked fewer than three.
- Moving a task from an earlier day to today goes through C1's
  `planScheduleChange()`, like every commitment, so it counts as the
  reschedule it is (keeping its time of day). That's C2's existing rule;
  "do it now" doesn't get an exemption.
- A new plan is committed `via: 'proposal'`, because `day_plans` only
  allows `'shutdown'` or `'proposal'`, and a CHECK change needs a table
  rebuild that isn't worth it for a label nothing reads yet. An existing
  plan keeps its original value.

**Break it down** replaces the task with smaller steps (one to eight; more
than that is a project, not a task):

- Each step is a new task linked to the original with
  `links(step → original, rel 'subtask_of')`. Each is filed under the
  original's project if it had one, and carries the original's deadline,
  since a real deadline applies to every piece of the work.
- The user chooses when the steps land: **Today** (the default),
  **Tomorrow**, or **Inbox, to decide later**. Today and tomorrow make them
  active and scheduled; the inbox leaves them undated for triage.
  Undated-but-active steps would vanish from every view, which is why
  there's no fourth option.
- Steps start with `touch_count` 0. Breaking a task down is a decision,
  and the pieces get a clean slate.
- The original is **archived** (`items.status = 'archived'`), not deleted
  and not completed. It's kept, its steps point at it, and it's out of
  every list. `status` has no CHECK constraint, so this needed no
  migration.
- Undo tombstones the steps and their links (Decision 2: never
  `DELETE FROM`) and restores the original's status.

**Let it go** (the plan's "kill it") offers **Move to someday**
(Decision 4's tier, out of Today, Revisit and every count, kept and
searchable) or **Delete** (a tombstone). The sheet says what each does.

**Every action is undoable** from the same 10-second toast as triage and
Today. The undo is the planner's own inverse writes, tested against a
real database including an ops-log replay.

## Three states (Decision 7)

| State  | What it shows                                                                                                                                                                 |
| ------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| empty  | "Nothing needs a second look. When a task keeps getting moved, it shows up here so you can decide what to do with it." One action: **Go to Today**                            |
| cold   | "Welcome back. There's nothing to catch up on here — these will keep until you're ready. A few, if you'd like to decide on them now:" — the top three, then **Show the rest** |
| loaded | "Tasks that keep getting moved. Each one needs a decision, not more effort: do it now, break it into smaller steps, or let it go." Then the ranked list                       |

There's no count of how many tasks are here in any state, including
"Show the rest" (Decision 4: no raw unbounded counts of outstanding work).

## Language review against Decision 7

Done explicitly, string by string:

| Where               | Text                                                                               | Review                                                                                                                                                    |
| ------------------- | ---------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Nav, title          | "Revisit"                                                                          | Chosen over "Slipping," which describes the user's tasks as failing. "Revisit" names what the view is for                                                 |
| Lede (loaded)       | "…needs a decision, not more effort"                                               | Puts the cause on the task's definition, not the user's discipline. That's the plan's own point: "either unimportant or badly defined"                    |
| Cold                | "nothing to catch up on… these will keep until you're ready"                       | No backlog framing, and it explicitly says waiting is fine. Shows three, not the list                                                                     |
| Empty               | "Nothing needs a second look."                                                     | Encouraging and neutral; explains what would appear here                                                                                                  |
| Detail              | "Moved 4 times, last on Thu 1 Oct" / "Planned for Sun 20 Sep"                      | Facts, as dates. No "overdue," "late," "N days ago," or "still not done." The move count is why it's ranked where it is, so it's shown rather than hidden |
| Actions             | "Do it now," "Break it down," "Let it go"                                          | "Kill it" (the plan's term) became "Let it go": the same action without violence or loss framing                                                          |
| Let it go sheet     | "Someday keeps … out of your lists and counts until you want it back."             | Someday is presented as a real choice, not a graveyard                                                                                                    |
| Break it down sheet | "The original is archived — kept, but out of your lists."                          | Reassures that nothing is lost                                                                                                                            |
| Replace sheet       | "Which one should … take the place of? The one it replaces stays on today's list." | Nothing is dropped from the day                                                                                                                           |
| Toasts              | "Added to today's three," "Split into 2 steps," "Moved to someday," "Deleted"      | Plain confirmations                                                                                                                                       |

No red, and no colour carries meaning (Decision 13). The cards differ only
by text and order.

`RevisitRoute.test.tsx` makes the review a regression test: the rendered
text in every state must not match
`overdue|late|behind|fail|missed|slipp|procrastinat|should have|neglect|ignored|forgot|still not|again|N tasks|N items`.

## Verification

```bash
pnpm verify      # typecheck + lint + format + unit tests + build
pnpm test:e2e    # Playwright, including e2e/revisit.spec.ts
```

| DoD requirement                                                       | Where                                                                                                                                                                                                                                        |
| --------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| slipping ranks by touch count with age as a tiebreaker, and is tested | `slipping.test.ts` (four moves beat twelve days untouched; more moves always win; equal moves → longest untouched; never-touched ages from creation; a total order; DST-safe day boundaries); `e2e/revisit.spec.ts` (the rendered order)     |
| each of the three actions works and is undoable                       | `slippingActions.test.ts` (each planner, then each through `mutate()` on a real database, undone, and replayed from the ops log); `RevisitRoute.test.tsx` (each action and each toast undo); `e2e/revisit.spec.ts` (all three, undo, reload) |
| the view is empty and encouraging when nothing is slipping            | `RevisitRoute.test.tsx` (empty state); `e2e/revisit.spec.ts` ("nothing slipping")                                                                                                                                                            |
| language contains no guilt framing — reviewed explicitly against D7   | The review table above; `RevisitRoute.test.tsx` checks every state's text against the guilt pattern                                                                                                                                          |
| Today and Revisit agree on "slipping"                                 | `slipping.test.ts` ("Today's carried-over bucket is exactly the slipping list, in the same order")                                                                                                                                           |

## Notes for later parts

- **Part C5 (amnesty):** someday tasks are already out of Revisit
  (`SLIPPING_SQL` excludes them). Amnesty's sweep shouldn't touch archived
  tasks: they're already out of every list, and un-archiving one would
  bring it back alongside its own steps.
- **Search (C5, "someday items remain searchable"):** archived tasks
  should probably be searchable too, labelled as broken down. `items_fts`
  already indexes them.
- **Part H5 (weekly review)** lists slipping. It should call
  `findSlipping()`, not re-derive it.
