# Phase B, Part B2 — Deterministic parser

Status: **done.**

## What's in place

- `src/capture/parse.ts` — `parse(input, now)`, pure and dependency-free
  (Decision 5). Recognizes, in a single left-to-right token scan:
  - dates and times: `today`, `tomorrow`, `mon`–`sun` (abbreviated or
    full), `next week`, `in N days`, `3pm`/`15:00`/`10am`, `21/8`,
    date+time combos (`tomorrow 3pm`), and `every <weekday>` (recurring)
  - `@name` → person, `#project` → container
  - `!`/`!!`/`!!!` → priority
  - a leading `*` → routine, a leading `?` → question
  - `~45m`/`~2h` → estimate
  - `tokenKey()` — identifies a token across re-parses (by `type:raw`), so
    the UI can remember which chips the user has dismissed.
  - `resolveCapture(input, removedKeys, now)` — what `CaptureRoute` calls
    on submit. Turns the still-active tokens into `{title, scheduledFor,
estimateMin}`.
- `src/capture/parse.test.ts` — 74 cases (comfortably past the 60-input
  DoD line), covering every pattern above, the documented ambiguous-date
  rule, the documented `!!!!`-doesn't-match rule, purity, and
  `resolveCapture`'s accept/reject behavior.
- `src/capture/captureTask.ts` — reworked to take already-resolved input
  (`{title, scheduledFor?, estimateMin?}`) instead of raw text, and to
  write `scheduled_for`/`estimate_min` onto `task_fields` when present.
- `src/routes/CaptureRoute.tsx` — renders a chip per active token below
  the field (`<ul aria-label="Parsed from your capture">`), each a button
  labeled `Remove {chip label}`. Submitting calls `resolveCapture()` with
  the current rejected-chip set, not `parse()` directly — see "Why
  `captureTask` takes resolved input" below.

## Why only dates and estimates get written anywhere

`task_fields` has real columns for `scheduled_for` and `estimate_min`
today. It has no column for priority, and `@person`/`#project` are
supposed to become `links` rows to auto-created entities — but
auto-creating a person is explicitly Part G1's job ("no separate add
contact form... `@name` creates a person on first use"), and nothing in
the plan authorizes B2 to reach ahead and build that. A `*`/`?` prefix
implies `kind='routine'`/`kind='note'`, but `routine_fields.cadence` is
`NOT NULL` with no cadence-parsing rule yet (that's Part E1), and
`note_fields.note_kind` is constrained to `journal|highlight|quote|idea`
— "question" isn't one of them.

So this part parses and displays all seven token types (the DoD's own
wording — "every parse result is visible as a chip" — doesn't say every
token type has to change the write), but only ever writes the two that
have a real field waiting for them. The other five are genuinely inert:
recognized, shown, dismissible, and otherwise inconsequential. Wiring them
up is each owning phase's job, not a debt B2 is leaving behind — there
was nowhere correct to put that data yet.

## A real bug this caught: stripping tokens the app can't act on

The first version of `resolveCapture()` stripped _every_ accepted token
from the title, not just date/estimate ones — so typing `Buy milk @Rahul`
and pressing Enter (no chip touched) would silently produce a task titled
just `Buy milk`, with `@Rahul` gone from the item and written nowhere
else. `parse.test.ts`'s very first `resolveCapture` test caught this
immediately (asserting the title kept `@Rahul`), before it ever reached
`CaptureRoute`. Fixed by narrowing `resolveCapture`'s stripping to
date/estimate tokens only — every other token type's raw text now stays
in `title` unconditionally, whether or not its chip is showing, because
nothing else currently gives that information anywhere else to live. A
dismissed person/project/priority/routine/question chip is purely a
display gesture — "stop suggesting this" — never a data-loss one.

## A second edge case: a capture that's _only_ a date/estimate

`resolveCapture('tomorrow')` strips the entire input, since "tomorrow" is
the whole string — the resulting title is empty, and `items.title` is
`NOT NULL`. Rather than silently dropping the capture (breaking "unparsed
input still produces a valid item"), `CaptureRoute` falls back to the raw
trimmed text as the title in that one case, while still applying
`scheduledFor`/`estimateMin` from the parse — so `tomorrow` alone becomes
a task literally titled "tomorrow", _and_ scheduled for tomorrow. The
fallback only ever changes what the title displays, never whether the
parsed fields get applied.

## Design choices behind the parsing rules

- **Ambiguous `DD/MM`, day always first.** The plan's own example (`21/8`)
  is only unambiguous under this rule (no month 21 exists), so it's the
  one the genuinely ambiguous case (`5/6`) follows too: day 5, month 6 —
  June 5th, not May 6th. Rolls to next year if that date has already
  passed this year. An out-of-range day or month (`40/13`) matches
  nothing and is left as plain text, rather than guessing.
- **A run of 4+ `!` matches nothing.** `!{1,3}` bounded by
  lookahead/lookbehind so it can't match inside a longer run — "!!!!" has
  no 1-3-length window that isn't adjacent to another `!`, so the whole
  run is left as plain text. Documented and tested (`parse.test.ts`'s
  `!!!!` case), the same treatment Part A2 gave `5/6`.
- **Same weekday as today resolves to today, not +7 days.** Typing `wed`
  on a Wednesday almost certainly means today, not next Wednesday — this
  also makes `every <weekday>`'s first occurrence consistent with the
  plain-weekday rule.
- **`*`/`?` only count as prefixes when they lead the (trimmed) input.**
  Elsewhere they're just punctuation — `"Did I already buy milk?"` doesn't
  become a question, `"Gym *"` doesn't become a routine. This is the
  plan's own wording ("a **leading** `?`"), not an invented restriction.
- **Combined tokens: alternation ordered longest/most-specific first.** A
  single global regex tries each date alternative left-to-right at a given
  position and takes the first match — it doesn't search for the longest
  overall match across alternatives — so `tomorrow 3pm` only resolves as
  one combined token because the combo alternative is listed before the
  bare-`tomorrow` one. Cross-category ordering (dates before mentions
  before priority before routine/question before estimate, matching the
  plan's own listing order) is enforced the same way, defensively, even
  though no two categories actually share a trigger character.
- **Duplicate identical tokens share one removal key.** `tokenKey()` is
  `type:raw`, not per-occurrence — rejecting one instance of a repeated
  token (e.g. two identical `!!` runs) rejects all of them. Documented as
  a deliberate simplification in `parse.ts`'s own comment, not a bug: this
  is capture-length text, where that scenario is rare enough not to be
  worth a positional key that would also have to survive re-parses as the
  user keeps typing.

## Verification

```bash
pnpm verify      # typecheck + lint + format + 227 unit tests (16 files) + build — green
pnpm test:e2e    # 11 Playwright tests — green, capture.spec.ts unaffected by the parser
```

| DoD requirement                                                                  | Where                                                                                                                                                       |
| -------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| a test table of at least 60 input strings maps to expected parse output          | `parse.test.ts` — 74 cases                                                                                                                                  |
| the parser is pure and dependency-free                                           | `parse.ts` has no imports; `parse.test.ts`'s "is pure" describe block asserts referential-equal repeat calls                                                |
| ambiguous input (`5/6`) resolves by a documented and tested rule                 | day-first `DD/MM`, documented in `parse.ts`'s `resolveNumericDate` comment and tested explicitly                                                            |
| every parse result is visible as a chip and individually removable before commit | `CaptureRoute.tsx`'s chip tray; `CaptureRoute.test.tsx`'s "parsed chips" describe block, and manually confirmed in the Browser pane (light and dark, 360px) |
| unparsed input still produces a valid item                                       | unchanged from B1 for plain text; the pure-date/estimate fallback above extends this to those cases too                                                     |

Manually verified beyond the automated suites: a five-token combined
capture (`Buy milk @Rahul #groceries !! tomorrow 3pm ~30m`) renders all
five chips correctly labeled; removing the date chip and submitting
produces an item titled with the literal `tomorrow 3pm` text and no
`scheduled_for`; chip background/text colors resolve to the correct
`--surface-raised`/`--ink` values in both themes; chips wrap without
horizontal overflow at 360px.
