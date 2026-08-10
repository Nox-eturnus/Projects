# Usage log

Tracks real usage against the plan's Definition of "used" and each phase
gate that depends on it (`life_helper_implementation_plan_v1.md`).
Self-reported is fine — this is a personal project — but it needs dates,
or the gate hasn't passed. Nothing in this file can be filled in by
running code or by an agent; it's a record of what actually happened on a
real device, kept honest by that requirement.

> **Definition of "used"** (from the plan): the app was opened on at
> least 5 of 7 consecutive days, on at least two different days from a
> phone, and at least one item was captured or completed on each of those
> days.

---

## Part B4 — Capture gate

Conditions, from `life_helper_implementation_plan_v1.md`'s Part B4:

| #   | Condition                                                                       | Status                                                                            |
| --- | ------------------------------------------------------------------------------- | --------------------------------------------------------------------------------- |
| 1   | Capture latency budget met on a real Android device, measured and recorded      | ✅ done — 20ms / 32ms / 30ms, 2026-08-07. See `docs/phase_B1_capture_surface.md`. |
| 2   | `ops` replay test passes with real captured data, not fixtures                  | ⬜ pending real usage — tool ready: `/gallery` → "Run ops replay verification"    |
| 3   | App installed to the Android home screen and used from there, not a browser tab | ⬜ pending                                                                        |
| 4   | 7 consecutive days meeting the Definition of "used"                             | ⬜ pending — needs the daily log below filled in                                  |
| 5   | At least 30 real items captured, not test data                                  | ⬜ pending — running total tracked below                                          |

**Do not proceed to Phase C until every row above is checked**, per the
plan's own rule for this gate. If the 7-day usage condition fails, the
plan's instruction is explicit: diagnose the friction that caused it and
fix it, then re-run the gate — not push through anyway.

### How to close out the remaining conditions

1. **Install to the home screen.** Open
   `https://life-helper.pages.dev` in Chrome on the phone, use "Add to
   Home Screen," and from then on always launch it from that icon, not a
   browser tab or bookmark.
2. **Use it daily for 7 consecutive days.** Capture whatever's actually
   on your mind as it comes up — this only works as a real signal if the
   items are real, not filler to hit the count. Fill in one row of the
   table below each day.
3. **After day 7**, if the daily log shows the gate conditions met: open
   `/gallery` on the phone (or any device sharing that install — the
   database is per-device, so run it on the one with the real usage
   history) and click "Run ops replay verification." Paste the result
   (pass/fail per table) below.
4. **Update the status table above** and mark this gate closed with
   today's date once all five rows are checked.

### Daily log

Fill in one row per day. "Items" is a running total, not a daily count,
so the last filled row shows whether the 30-item condition is met.

| Date | Opened? | From phone? | Item(s) captured/completed today | Running item total | Notes |
| ---- | ------- | ----------- | -------------------------------- | ------------------ | ----- |
|      |         |             |                                  |                    |       |
|      |         |             |                                  |                    |       |
|      |         |             |                                  |                    |       |
|      |         |             |                                  |                    |       |
|      |         |             |                                  |                    |       |
|      |         |             |                                  |                    |       |
|      |         |             |                                  |                    |       |

### Ops replay verification result

Run from `/gallery` once real usage exists — not before, and not against
seeded/test data (that defeats the point of this specific gate
condition).

- Date run:
- Result: ⬜ pass / ⬜ fail
- Table-by-table detail (paste from the results table, or note the first
  mismatch if it failed):

---

## Part C6 — Today gate (for later)

Same format, 14 consecutive days. Not started — Phase C hasn't begun.
