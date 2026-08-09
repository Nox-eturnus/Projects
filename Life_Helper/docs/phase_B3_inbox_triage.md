# Phase B, Part B3 — Inbox and triage ritual

Status: **done.**

## What's in place

- `src/triage/triageActions.ts` — `planTriageAction(item, action, now)`,
  pure and synchronous. Each of the plan's eight actions (schedule for
  today, schedule for a date, file to a project, convert to note, convert
  to routine, someday, done, delete) produces a forward `Write[]` _and_
  its exact inverse `undoWrites`, computed from a snapshot of the item's
  current row. The undo toast's 10-second window (Part B3's own DoD) is
  just "run `undoWrites` through the same `mutate()` the forward action
  used" — there's no bespoke per-action revert logic to keep in sync.
- `src/triage/triageActions.test.ts` — one test per action, forward and
  undo shapes.
- `src/routes/InboxRoute.tsx` — lists `status='inbox'` items newest
  first (Decision 7's three states), with a "Start triage" entry point.
- `src/routes/TriageView.tsx` — the one-item-at-a-time ritual. Keyboard:
  `T` today, `D` date, `P` project, `N` note, `R` routine, `S` someday,
  `Enter` done, `Backspace`/`Delete` delete — disabled while a Sheet is
  open so typing in the date picker can't trigger an action. Touch: swipe
  right on the card = done, swipe left = someday; all eight actions are
  also always reachable as buttons, since a swipe-only surface would hide
  six of them from mobile users entirely.
- `src/ui/AppShell.tsx` gained an "Inbox" nav link; `/inbox` registered
  in `src/App.tsx`.
- `e2e/triage.spec.ts` — three Playwright tests against the real
  worker + sqlite-wasm pipeline: 20 items triaged by keyboard alone
  (timed), undo, and leaving mid-way.

## Status vocabulary: `'inbox'` → `'active'` or `null`, nothing fancier

The schema's own comment calls `items.status` "kind-specific vocabulary"
with no enforced values. B3 needed to pick something, so: every action
that keeps `kind='task'` (schedule today/date, file to project, someday,
done) sets `status='active'` — it's no longer awaiting triage, and
Decision 4's `someday`/`completed_at` fields (not `status`) already carry
the more specific state. Every action that changes `kind`
(convert-to-note, convert-to-routine) sets `status=null`, since a task's
`'inbox'`/`'active'` vocabulary doesn't mean anything for a note or
routine — Parts G4 and E1 own defining what (if anything) `status` means
for those kinds. Undo restores whatever `status` was actually there
before (not hardcoded back to `'inbox'`), so an action taken on an
already-triaged item — not possible through this UI today, but not
precluded by the write layer either — would still undo correctly.

## Two schema-shaped compromises, both documented and both temporary

- **Convert to note writes `note_kind='idea'`.** `note_fields.note_kind`
  is constrained to `journal|highlight|quote|idea`; none of the four is a
  real fit for "a task someone decided wasn't actionable right now," and
  Part G4 is where that vocabulary actually gets designed. `'idea'` is
  the least-wrong bucket available today, not a considered design choice
  — worth revisiting when G4 exists.
- **Convert to routine writes `cadence='daily'`.** `routine_fields.cadence`
  is `NOT NULL` with no cadence-parsing UI yet (Part E1 owns that). A
  hardcoded default is honest about the gap — the alternative was
  blocking the triage action entirely on a phase that isn't built, which
  would contradict the plan's own ordering (B3 before E1).

Both are recorded here so they're a deliberate, visible choice rather
than something a future phase discovers by surprise.

## "File to project" only ever links to an existing project

Part F ("Container model") is what actually builds project creation;
nothing in B3's plan text asks it to reach ahead and build that too. The
project-picker Sheet queries `kind='project'` items and offers to link to
one; on a fresh install, with no Part F yet built, it correctly shows "No
projects yet." — not a missing feature, just an accurate reflection of
what exists.

## "Leaving triage mid-way loses nothing" is architectural, not a special case

Every triage action commits immediately through `dbClient.mutate()`, the
same as capture (Decision 3's "capture never blocks" cousin for triage:
there's no staging/draft state an in-progress session could lose).
Exiting triage, closing the tab, or the browser crashing mid-session
all leave exactly the items already actioned as actioned and the rest
untouched — this needed no code of its own to guarantee, only _not_
building a batch-commit flow. `e2e/triage.spec.ts` proves the observable
behavior (exit after one action → the other item is still there, durably,
confirmed via a fresh SQL query), not the absence of a bug that isn't
structurally possible to begin with.

## Two real bugs `e2e/triage.spec.ts` caught

**The undo toast disappeared for the last item of a session.**
`TriageView`'s "inbox zero" completion message and its main triage view
were two different early-return branches — and only the main branch
rendered the undo toast. Triaging the _last_ remaining item flips
`items.length` to 0 in the same tick the toast should appear, so the
component switched straight to the empty-state branch and the toast (and
its 10-second undo option) never rendered at all. First caught by
`e2e/triage.spec.ts`'s undo test hanging waiting for a button that never
appeared, not reasoned about in advance. Fixed by hoisting the toast into
a shared value rendered in both branches.

**The undo toast could be covered by the PWA's own toast.** Once the
first bug was fixed, the undo click still failed — Playwright reported
`<div role="status" class="_toast_...">` intercepting the click,
persistently, not a one-frame flicker. `PwaPrompts.module.css`'s toast
(the "ready to work offline"/"update available" banner) is _also_
`position: fixed`, bottom-centered, and carries `z-index: 1000`; mine had
no `z-index` at all. Diagnosed by instrumenting a throwaway Playwright
script to poll `elementFromPoint` at the undo button's coordinates over
two seconds (see the test run in the session this part was built in) —
the two toasts' bounding boxes genuinely overlap, and the PWA one always
wins a stacking contest it has no business being in during a time-limited
undo window. Fixed with `z-index: 1001` on the triage toast, so it always
wins if the two ever coincide (a real scenario: a service-worker update
becoming available mid-triage-session, not a hypothetical). This is a
narrow fix for this one collision, not a general toast-stacking system —
worth a shared convention if a third toast type shows up.

## Verification

```bash
pnpm verify      # typecheck + lint + format + 263 unit tests (19 files) + build — green
pnpm test:e2e    # 14 Playwright tests, including all 3 triage.spec.ts scenarios below — green
```

| DoD requirement                                                   | Where                                                                                                                                               |
| ----------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| an inbox of 20 items triaged in under 90s using only the keyboard | `e2e/triage.spec.ts`: seeds 20 real items, triages by keyboard alone, asserts elapsed time                                                          |
| every action is undoable for 10 seconds via a toast               | `triageActions.test.ts` (forward/undo write shapes); `TriageView.test.tsx` (toast, timer, replacement); `e2e/triage.spec.ts` (real undo round-trip) |
| leaving triage mid-way loses nothing                              | `e2e/triage.spec.ts`: exit after one of two items, confirm the untouched one survives via direct SQL query                                          |
| all three view states are implemented                             | `InboxRoute.test.tsx`: empty/cold/loaded; manually confirmed in the Browser pane (dark mode, 360px)                                                 |

Additionally verified manually in the Browser pane beyond the automated
suites: triage action buttons and their `<kbd>` hints render correctly in
dark mode (tokens resolve to the measured dark palette); the 8-button
action grid wraps without horizontal overflow at 360px.
