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
| 2   | `ops` replay test passes with real captured data, not fixtures                  | ✅ done — 2026-08-22, all tables match. See result below.                        |
| 3   | App installed to the Android home screen and used from there, not a browser tab | ✅ done — installed via "Add to Home Screen", launched from the icon throughout.  |
| 4   | 7 consecutive days meeting the Definition of "used"                             | ✅ done — 9 consecutive days, 2026-08-11 to 2026-08-19, all from phone.           |
| 5   | At least 30 real items captured, not test data                                  | ✅ done — 31 (low estimate) to 36 (high estimate), 2026-09-11. Clears 30 under either estimate. |

**Do not proceed to Phase C until every row above is checked**, per the
plan's own rule for this gate. If the 7-day usage condition fails, the
plan's instruction is explicit: diagnose the friction that caused it and
fix it, then re-run the gate — not push through anyway.

**Gate closed: 2026-09-11.** All five conditions above are checked.

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

| Date       | Opened? | From phone? | Item(s) captured/completed today                 | Running item total | Notes |
| ---------- | ------- | ----------- | -------------------------------------------------- | ------------------- | ----- |
| 2026-08-11 | Yes     | Yes         | Acne cream, wash face                               | —                    |       |
| 2026-08-12 | Yes     | Yes         | Acne cream, wash face                               | —                    |       |
| 2026-08-13 | Yes     | Yes         | Acne cream, wash face                               | —                    |       |
| 2026-08-14 | Yes     | Yes         | Acne cream (3pm), wash face (5pm)                   | —                    | Times shifted earlier this day |
| 2026-08-15 | Yes     | Yes         | Acne cream, wash face, + occasional item (see notes)| —                    |       |
| 2026-08-16 | Yes     | Yes         | Acne cream, wash face                               | —                    |       |
| 2026-08-17 | Yes     | Yes         | Acne cream, wash face, + occasional item (see notes)| —                    |       |
| 2026-08-18 | Yes     | Yes         | Acne cream, wash face                               | —                    |       |
| 2026-08-19 | Yes     | Yes         | Acne cream, wash face, + occasional item (see notes)| ≈15–20 (aggregate self-report) | Recurring: acne cream (6pm, one day 3pm) + wash face (8pm, one day 5pm), triaged to "today" via Inbox. Occasional extras across the 9 days: bring clothes up to room, remove clothes before rain, turn off stove in 15 min. Exact per-day counts not tracked — total is a self-reported aggregate, not a precise ledger. |
| 2026-08-22 | Yes     | Yes         | Apply cream (3pm), F1 Sprint (3:30pm), wash face (5pm), F1 Quali (7:30pm) — all done | 19 (low-end) – 24 (high-end) | 4 items this day |
| 2026-08-23 | Yes     | Yes         | F1A race (2:00pm), F1 race (6:30pm), apply acne cream (3pm) — all done | 22–27 | 3 items this day |
| 2026-08-25 | Yes     | Yes         | Wash acne cream after 2h, pack for trip in 10 min — both done | 24–29 | 2 items this day |
| 2026-08-26 | Yes     | Yes         | Flight at 11:00am — done | 25–30 | 1 item this day |
| 2026-08-28 | Yes     | Yes         | Eat lunch in 15 min — done | 26–31 | 1 item this day |
| 2026-08-30 | Yes     | Yes         | Apply cream (3pm), wash face (5pm) — both done | 28–33 | 2 items this day |
| 2026-08-31 | Yes     | Yes         | Wash face in 2 hours — done | 29–34 | 1 item this day. |
| 2026-09-11 | Yes     | Yes         | Wash face after 2 hours, food order reminder (8:15pm) | 31–36 | 2 items this day. Low-end running total (baselined off the "≈15" floor of the earlier aggregate) now sits at 31 — clears the 30 threshold even under the conservative estimate. High-end (baselined off "≈20") sits at 36. |

### Ops replay verification result

Run from `/gallery` once real usage exists — not before, and not against
seeded/test data (that defeats the point of this specific gate
condition).

- Date run: 2026-08-22
- Result: ✅ pass
- Table-by-table detail: "All tables match" — every row in the results
  table showed pass.

---

## Part C6 — Today gate (for later)

Same format, 14 consecutive days. Not started — Phase C hasn't begun.
