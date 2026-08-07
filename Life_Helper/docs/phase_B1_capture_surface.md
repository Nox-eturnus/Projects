# Phase B, Part B1 — Capture surface

Status: **done**, except two Android-device-only Definition of Done lines
(see "What's deferred to a real device" below) — this session has no
physical Android hardware to measure against.

## What's in place

- `src/db/id.ts` — `generateItemId()`, a UUIDv7 (RFC 9562) generator. This
  is the first part that actually creates an `items` row from the client,
  so it's the first part that needed one: Decision 2 requires every
  entity's primary key to be a client-generated UUIDv7, never an
  autoincrement integer. `src/db/id.test.ts` asserts the version/variant
  nibbles, that the leading 48 bits round-trip the millisecond timestamp
  it was called with, and that ids generated with increasing timestamps
  sort lexicographically.
- `src/capture/captureTask.ts` — the write path. One `mutate()` call with
  two writes (`items` with `kind='task'`/`status='inbox'`, plus its
  `task_fields` side-table row) so the pair is atomic, per Part A3's own
  note that "capture never blocks" requires creating an item and its
  side-table row as one write, not two. Pure aside from injected
  `mutate`/`generateId`/`now`, so `captureTask.test.ts` unit-tests it
  without a real `dbClient`.
- `src/capture/useGlobalCaptureShortcut.ts` — binds Ctrl/Cmd+K globally.
  Navigates to `/capture` from anywhere; if already there, dispatches a
  `life-helper:focus-capture` `Event` instead (a same-path `navigate()`
  wouldn't remount the route, so nothing would otherwise refocus the
  field if the user had clicked away from it).
- `src/routes/CaptureRoute.tsx` + `.module.css` — the capture surface
  itself: a `<textarea>` (not `<input>`, since Shift+Enter must be able to
  insert a literal newline), a large mic button, and a "Recently
  captured" panel built on `ThreeStateView` (Decision 7).
- `src/App.tsx` — mounts `useGlobalCaptureShortcut()` once, inside
  `RouterProvider` and above any single route (a new `AppRoutes`
  component), and registers `/capture`. `src/ui/AppShell.tsx` gained a
  "Capture" nav link — not asked for explicitly, but without one, a
  mobile user with no keyboard has no way to reach capture at all except
  guessing a URL.
- `src/test/setup.ts` gained a `navigator.locks` and `Worker` shim (see
  "A pre-existing test-infrastructure gap" below).
- `e2e/capture.spec.ts` — five Playwright tests against the real
  worker + sqlite-wasm + OPFS pipeline: the global shortcut, offline
  capture, Shift+Enter, focus retention across consecutive captures, and
  reload persistence.

## Design decisions not spelled out in the plan

**No pending/disabled state while a write is in flight, by design, not by
omission.** The first implementation set `pending` state and disabled the
textarea during the `mutate()` await, then called `.focus()` in a
`finally` block once it resolved. That is a real bug, not a hypothetical
one — it was caught by `e2e/capture.spec.ts` itself, not reasoned about in
advance: React state updates aren't applied to the DOM synchronously, so
calling `.focus()` in the same tick as `setPending(false)` runs against an
element that is, at that exact instant, still `disabled` in the DOM —
browsers silently refuse to focus a disabled element, so the field was
left permanently blurred after every real capture. Rather than reach for
`flushSync` or a `requestAnimationFrame` delay to patch around the timing,
the fix follows Decision 3 more literally: capture must never block, so
the field now clears immediately on Enter and `captureTask()` fires
without the UI waiting on it at all. Nothing is disabled, focus never
moves, and there's no timing window to get wrong. A capture that somehow
fails writes nothing and is silently lost from the UI's perspective — an
explicit non-goal per Decision 3 ("no confirmation, no modal"); Part B3's
triage/undo machinery is the place error surfacing would belong, not B1.

**"Recently captured" gives capture a re-entry story it wouldn't
otherwise have.** Decision 7 requires every view to implement
empty/cold/loaded, but a bare capture box has no state of its own to
speak of. The chosen interpretation: query the 5 most recent
`status='inbox'` tasks and treat the most recent one's `created_at` as
this view's "last active" signal for `computeViewState()`. Empty means
nothing has ever been captured; cold means the most recent capture is 3+
days old (Decision 7's absence threshold) — welcoming, not "you have N
overdue items"; loaded lists them. This also happens to give capture
something Decision 3 doesn't ask for but clearly wants implicitly: visual
confirmation that a capture actually landed, since the field itself gives
none (it just goes blank).

**The mic button's only job is `.focus()`.** The plan is explicit that
this part must not implement speech recognition, bundle a model, or call
a transcription API — Android's own keyboard dictation already covers it
for free once the system keyboard is showing. A button that only focuses
the field looks like it does nothing, but "does nothing beyond what the
platform already provides" is the literal requirement here.

## A pre-existing test-infrastructure gap, fixed in passing

This is the first part where a component (`CaptureRoute`, via `useQuery`)
imports `src/db/client.ts` — Parts A3/A4 exercised the db layer and the UI
primitives separately, never together through a rendered component. That
exposed two jsdom gaps at once, both in the same spot Part A4 found the
`HTMLDialogElement.showModal` gap: `src/test/setup.ts`.

- **`navigator.locks` doesn't exist in jsdom 30 at all** — not a stub that
  throws, the property is simply absent. `DbClient`'s constructor calls
  `navigator.locks.request(...)` inside its async `init()`, so the module
  import alone (in _any_ test file that imports a component which
  transitively imports `db/client.ts` — including `App.test.tsx`, which
  never even renders `CaptureRoute`'s content) threw an unhandled
  rejection and failed the whole run. A minimal same-tab-only polyfill is
  enough: nothing in a unit test needs real cross-tab lock queueing, only
  that `request()` grants once and doesn't throw.
- **`Worker` doesn't exist in jsdom either.** Once the lock polyfill lets
  `setUpAsLeader()` proceed, it reaches `new Worker(...)`, a synchronous
  `ReferenceError` inside an async method — another unhandled rejection.
  A `Worker` stub whose `postMessage()` is inert is enough: Comlink calls
  against it (e.g. `api.init()`) simply never resolve, which is a silent
  no-op for every test that doesn't depend on a real, responsive
  `dbClient` — i.e. every test in this codebase, since `CaptureRoute`'s
  own test mocks `db/client` outright for anything that needs real
  request/response behavior.

Neither gap is specific to capture — any future component that imports
`dbClient` would have hit both. Fixing them in `test/setup.ts` once, the
same file Part A4 already established as the place for jsdom-limitation
workarounds, means Part C and later don't rediscover this.

## What's deferred to a real device

Two Definition of Done lines are Android-hardware-only and this session
had no physical device to measure against:

- **keypress-to-persisted under 200ms, measured on a mid-range Android
  device.** What _is_ verified: `captureTask()` called directly against a
  real worker+OPFS `dbClient` in a desktop Chromium browser resolved in
  ~80–120ms end-to-end (two writes, six `ops` rows), comfortably inside
  budget on hardware far slower than a modern mid-range phone would be
  for the same local-only SQLite write — but this is not a substitute for
  the device measurement the plan asks for.
- **dictation produces text in the field on Android.** The mechanism
  (focus the field, let the system keyboard's own mic button handle it —
  see "Design decisions" above) has no code path for this repo to get
  wrong beyond focusing correctly, which e2e-tests do cover, but the
  actual dictation behavior is entirely the OS keyboard's, unverifiable
  without a device.

Record both against a real device before treating Part B4's capture gate
as satisfied.

## Verification

```bash
pnpm verify      # typecheck + lint + format + 141 unit tests (17 files) + build — green
pnpm test:e2e    # 11 Playwright tests, including all 5 capture.spec.ts scenarios below — green
```

| DoD requirement                                             | Where                                                                                     |
| ----------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| capture works fully offline, network disabled               | `e2e/capture.spec.ts`: offline test (`context.setOffline(true)` before typing/submitting) |
| keypress-to-persisted < 200ms on a mid-range Android device | **Deferred** — see "What's deferred to a real device"                                     |
| the input never loses focus between consecutive captures    | `e2e/capture.spec.ts`: consecutive-captures test; `CaptureRoute.test.tsx` unit-level      |
| dictation produces text in the field on Android             | **Deferred** — see "What's deferred to a real device"                                     |
| all three view states from Decision 7 are implemented       | `CaptureRoute.test.tsx`: empty/cold/loaded tests; manually confirmed in the Browser pane  |

Additionally verified manually in a real browser (Claude Code Browser
pane) beyond what's captured by the tables above: the shell renders
correctly at 360px (no horizontal overflow, mic button is a 48×48 touch
target) and in dark mode (tokens switch to the measured dark palette);
Ctrl+K opens `/capture` and focuses the field from the Today route; a
captured item appears newest-first and survives a real page reload.
