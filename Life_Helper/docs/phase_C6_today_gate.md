# Phase C, Part C6 — Today gate

Status: **tooling done; the gate itself is not passed yet.** Like B4,
this is a usage gate, not a build. Fourteen days of real use can't come
from code, and nothing here fakes it.

What this part does differently from B4: B4's log was self-reported, with
estimated totals. Here, every condition is **measured on the phone from
what actually happened**, and the report shows the evidence behind each
verdict. You still record the result in `docs/usage_log.md`; the app
never marks the gate passed by itself.

## The conditions, and how each is measured

The plan's gate, fixed before execution and not negotiable after:

| #   | Condition                                                  | Measured from                                                                                                                                                                                                                                                                                                                         | Passes when                                                                                                                                                                                          |
| --- | ---------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Today renders in under 1.5s cold start, real Android       | Each load that **starts** on Today records `performance.now()` on the frame after Today renders with its data, so from navigation start through fetching the app, starting SQLite on OPFS, Today's queries, and paint. Loads that start elsewhere, and back/forward restores, aren't cold starts. Tagged Android or not by user agent | The **median** of at least 3 Android samples is under 1500ms. One fast run could be luck; a median can't be gamed                                                                                    |
| 2   | Calendar sync survives a full week, no manual intervention | Every calendar refresh records its outcome per day. Saving the connection in Settings records an intervention and restarts the span                                                                                                                                                                                                   | A successful refresh 7+ local days after the first success, with no `reconnect_required`, `unauthorized` or `not_configured` in between. Offline and Google hiccups don't count: they fix themselves |
| 3   | Shutdown on at least 5 of 7 days                           | `day_plans.shutdown_completed_at`, which C2 already stamps                                                                                                                                                                                                                                                                            | 5+ of the 7 days ending today, or ending yesterday, since tonight's shutdown is usually still ahead                                                                                                  |
| 4   | 14 consecutive days meeting the Definition of "used"       | Every capture (`items.created_at`, deleted items excluded) and completion (`task_fields.completed_at`), grouped by local day. Days opened are recorded too, for the table                                                                                                                                                             | 14 consecutive days, ending today or yesterday, each with something captured or completed, on a phone                                                                                                |
| 5   | At least one amnesty sweep on real data                    | `amnesty_sweeps` rows not undone                                                                                                                                                                                                                                                                                                      | At least one                                                                                                                                                                                         |

**On "14 consecutive days meeting the Definition of 'used'".** The
Definition ("opened on at least 5 of 7 consecutive days … at least one
item captured or completed on each of those days") is about a 7-day
window, so "14 consecutive days meeting it" can be read two ways:

- **14 days in a row, each with a capture or completion.** This is the
  reading used here: it's the stricter of the two, and it's how B4's own
  log counted ("9 consecutive days").
- **A 14-day span in which every week has 5 or more used days.**

The day-by-day table shows every day, so either reading can be checked
by eye.

**"From a phone."** Until Phase D syncs devices, each device has only its
own database. The report runs on the phone, and every day it counts
happened on that phone. A desktop run says so and doesn't pass
condition 4.

## What's in place

- `src/gate/gateLog.ts` — the per-device logs no table already held:
  - cold starts (newest 30);
  - days the app was opened (newest 60);
  - calendar refresh outcomes per day (newest 60 days), with the first
    and latest success and when the connection was last saved.

  They live in localStorage because they describe this device's
  experience, not your data, so they mustn't sync. Each read tolerates
  missing or malformed storage.

- `src/gate/useGateRecorders.ts` — `useRecordColdStart()` (used by Today)
  and `useRecordOpens()` (used by the app shell, on launch and on
  returning to the foreground).
- Hooks in `useCalendar` (each refresh's outcome) and `saveConnection()`
  (manual intervention).
- `src/gate/gate.ts` — each condition as a pure function returning a
  verdict and one line of evidence, plus the three read-only queries it
  needs.
- `src/routes/GateRoute.tsx` (`/gate`, linked from Settings → Tools →
  "Today gate report"):
  - every condition with its evidence;
  - a 21-day day-by-day table (opened, captured or completed, shutdown,
    calendar);
  - the cold-start samples;
  - a **Copy report** button for the usage log.

  It isn't in the nav: like `/gallery`, it's a tool, not a destination.

Nothing new leaves the device. The logs are local and only ever read on
the device.

## How to run the gate

1. **Use the app as normal on the phone, from the home-screen icon,** for
   at least 14 days. Capture or complete at least one thing every day,
   and do the evening shutdown most evenings.
2. **Cold starts:** on at least 3 separate occasions, fully close the app
   (swipe it away from recents), then launch it from the icon. Those
   launches are what condition 1 measures.
3. **Calendar:** leave it connected, and don't re-enter the key unless
   something breaks. It needs a week of working refreshes.
4. **One fresh start**, once some tasks have gone untouched past the
   threshold. If nothing qualifies in time, lower the threshold in
   Settings (minimum 7 days).
5. **Then open Settings → Today gate report on the phone,** tap **Copy
   report**, and paste it into `docs/usage_log.md` under Part C6 (or send
   it to me to record).

**If the usage condition fails twice, the plan's Decision 12 stop rule
applies:** redesign Today rather than moving on to Phase D.

## Verification

```bash
pnpm verify      # typecheck + lint + format + unit tests + build
pnpm test:e2e    # Playwright, including e2e/gate.spec.ts
```

- `gate.test.ts` covers each rule:
  - the cold-start median, its minimum sample count, and the
    exactly-at-budget case;
  - the calendar week, including across a DST fall-back, with transient
    problems ignored and earlier problems out of scope;
  - both shutdown windows;
  - streaks broken by a single gap, and phone-only;
  - kept sweeps.

  It also runs the three gate queries against a real database.

- `gateLog.test.ts` covers the logs' bounds, counting, span resets
  (including through `saveConnection()`), malformed storage, and
  user-agent detection.
- `GateRoute.test.tsx` covers nothing recorded, everything met (all five
  pass), the day table, and copying the report.
- `e2e/gate.spec.ts`:
  - a real load that starts on Today records a cold start the report
    shows;
  - a load that starts elsewhere doesn't.
