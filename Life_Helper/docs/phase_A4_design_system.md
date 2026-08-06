# Phase A, Part A4 — Design system and shell

Status: **done.**

## What's in place

- `src/ui/tokens.css` — color tokens (light default, dark via `prefers-color-scheme` or a manual `data-theme` override), type scale, spacing scale, radii, and elevation. Every hex value comes from Decision 13 (the icon-sampled palette); the dark palette is a fresh measurement derived from the icon's deep green, not an inversion of the light one.
- `src/ui/contrast.ts` — the same token hex values as pure data, plus `contrastRatio()` (WCAG 2.1 relative-luminance formula) and a computed `contrastPairs` list. This is the single source of truth behind the table below, the regression test, and the gallery's own contrast table — the numbers are computed once, not copied by hand into three places.
- `src/ui/contrast.test.ts` — asserts every `ink`/`ink-secondary` pair against both surfaces, in both themes, meets the 4.5:1 AA minimum for normal text. A future edit to a token that breaks contrast fails `pnpm verify`, not just this doc.
- `src/ui/Button.tsx`, `Input.tsx`, `ListRow.tsx`, `Sheet.tsx` — the four required primitives, each a component + CSS module using only `var(--token)` colors, with visible `:focus-visible` states.
- `src/ui/ThreeStateView.tsx`, `EmptyState.tsx` — Decision 7's `empty`/`cold`/`loaded` contract as a component: all three props are required, so a future view that forgets one state is a compile error, not a missed review comment. `computeViewState()` shares Decision 7's "3+ days" absence threshold so every view agrees on it.
- `src/ui/router.tsx` — a minimal History-API router (`RouterProvider`, `useRouter`, `Routes`, `Link`): exact-path matching only, no params, no nesting.
- `src/ui/AppShell.tsx`, `AppShell.module.css` — header, primary nav, and main content region. Nav is a left sidebar at ≥768px and a fixed bottom tab bar below it, from one set of markup (see "Responsive nav" below).
- `src/ui/ThemeToggle.tsx` — cycles system → light → dark → system, persisted to `localStorage`. Exists so both themes can be inspected without changing the OS setting.
- `src/routes/GalleryRoute.tsx` (at `/gallery`) — renders every primitive, both three-state legs, and a live table of every `contrastPairs` entry with its measured ratio and pass/fail against AA.
- `src/App.tsx` now mounts `RouterProvider` → `AppShell` → `Routes` (`/` placeholder, `/gallery` the gallery), replacing the bare placeholder markup Part A1 left in place.

## Router: hand-rolled, not a library

The plan doesn't prescribe a router. Every route the plan lists through Phase G (`/inbox`, `/today`, `/routines`, `/projects`, `/library`, `/search`, ...) is a flat, single-segment, paramless page — there's no nesting and no dynamic segment anywhere in the spec yet. Pulling in a router library now for two routes (`/` and `/gallery`) would be exactly the kind of premature abstraction the project avoids elsewhere; `src/ui/router.tsx` is ~70 lines built on `history.pushState`/`popstate`, and gives real URLs (so a future push-notification deep link is just `navigate(path)`). If a route ever needs params or nesting, swapping in a real router is a contained, one-file change — nothing else in the app talks to `router.tsx` except through `useRouter()`/`Routes`/`Link`.

## Color tokens: names as a contrast fence

Decision 13 measured that only the two greens (`#505e53`, `#616d60` in light mode) pass WCAG AA against the paper surface; the warm grey and tan fail (2.85:1, 1.83:1) and must never carry text. `tokens.css` encodes that as naming, not comments: `--ink` / `--ink-secondary` are the only tokens a component may use for text color, while `--muted-fill` / `--muted-stroke` / `--accent-fill` / `--accent-stroke` describe what they may be used _for_ (fills, strokes) rather than implying a ramp step like `--accent-500` that invites reaching for it as text by habit.

### Dark mode: derived, then re-measured

Per Decision 13, dark mode is not an inversion of the light tokens. The base surface is a dark desaturated version of the icon's backing green; ink becomes the cream. Every pair was re-measured with the same `contrastRatio()` function, not assumed to inherit the light mode's ratios:

| Pair                                                   | Theme | Ratio     | AA (≥4.5:1, text) |
| ------------------------------------------------------ | ----- | --------- | ----------------- |
| `--ink` on `--surface-paper`                           | light | 6.42 : 1  | pass              |
| `--ink` on `--surface-raised`                          | light | 5.81 : 1  | pass              |
| `--ink-secondary` on `--surface-paper`                 | light | 5.10 : 1  | pass              |
| `--ink-secondary` on `--surface-raised`                | light | 4.61 : 1  | pass              |
| `--muted-fill` on `--surface-paper` (decorative only)  | light | 2.85 : 1  | n/a — never text  |
| `--accent-fill` on `--surface-paper` (decorative only) | light | 1.83 : 1  | n/a — never text  |
| `--ink` on `--surface-paper`                           | dark  | 13.11 : 1 | pass              |
| `--ink` on `--surface-raised`                          | dark  | 11.35 : 1 | pass              |
| `--ink-secondary` on `--surface-paper`                 | dark  | 8.55 : 1  | pass              |
| `--ink-secondary` on `--surface-raised`                | dark  | 7.40 : 1  | pass              |
| `--muted-fill` on `--surface-paper` (decorative only)  | dark  | 4.07 : 1  | n/a — never text  |
| `--accent-fill` on `--surface-paper` (decorative only) | dark  | 4.48 : 1  | n/a — never text  |

Every row above is `src/ui/contrast.ts`'s `contrastPairs`, rendered live at `/gallery` — this table is a snapshot of that computation, not a separate hand-maintained set of numbers. The muted/accent rows happen to clear 4.5:1 in dark mode too, but the policy (decoration only, never the sole signal for state, per Decision 13) applies regardless of whether a given mode's numbers would technically allow it — consistency across themes matters more than claiming a technicality in one of them.

Focus rings use `--focus-ring` (aliased to `--ink`), which is ≥6:1 against every surface in both themes — comfortably past the 3:1 WCAG 2.1 non-text-contrast minimum for UI indicators.

## Responsive nav: one set of markup, not two

`AppShell` renders a single `<nav>` with one list of links. Below 768px it's `position: fixed` to the bottom of the viewport (a tab bar); at 768px and above it becomes a static left sidebar — both are CSS-only (`@media` in `AppShell.module.css`), not two parallel DOM trees gated by JS. That matters for the tab-order requirement: because there's exactly one copy of each nav link in the DOM, whichever breakpoint is active, keyboard tab order is always skip-link → header controls → nav links → main content, with no hidden-but-focusable duplicate to trip over. Verified directly in the Browser pane at both 360px and 1920px (see "Verification" below).

## Sheet: native `<dialog>`, and the jsdom gap it exposed

`Sheet.tsx` uses a real `<dialog>` element with `showModal()`/`close()` rather than a hand-rolled overlay, for the same reason Part A3 chose Comlink over a hand-rolled RPC protocol: focus trapping, `Esc`-to-close, and top-layer stacking are exactly what the platform already does correctly.

Found while writing `Sheet.test.tsx`: jsdom 30.0.1 (this project's unit-test DOM) has no `HTMLDialogElement.showModal`/`close` at all — not a stub that throws, `typeof dialog.showModal` is `undefined`. `lib.dom.d.ts` types these as always present, so the optional-chained calls in `Sheet.tsx` needed an explicit `eslint-disable-next-line @typescript-eslint/no-unnecessary-condition` — the chain is only "unnecessary" from TypeScript's point of view, not jsdom's. The tests themselves query with `{ hidden: true }`, since a `<dialog>` without a real `open` attribute is `display: none` by the UA stylesheet and therefore outside the accessibility tree — that's a jsdom limitation being worked around in the test, not a statement about the component's real accessibility (confirmed manually in a real browser: `showModal()` sets `open` and the dialog is fully interactive — see "Verification").

## Two pre-existing hardcoded colors, fixed as part of "no color outside the token file"

The Definition of Done requires no hardcoded color outside the token file. Two pre-A4 spots used the old placeholder palette from before Decision 13's icon-derived colors existed, and both are now colors that would visibly clash with the icon on a home screen:

- `src/pwa/PwaPrompts.module.css` — the install/update toast used `#141221`/`#7c5cff`/`#f4f2ff` (a dark purple, left over from before the icon existed). Now `var(--ink)` / `var(--surface-paper)`, matching `Button`'s primary variant.
- `index.html`'s `<meta name="theme-color">` and `vite.config.ts`'s manifest `background_color`/`theme_color` — these drive the Android splash screen and browser chrome tint, which is exactly the surface Decision 13 says must "read as the same product" as the icon. A stray purple splash screen would fail that requirement on every cold launch. These can't reference `tokens.css` (manifest JSON and a static `<meta>` tag are evaluated with no build-time access to CSS custom properties), so they're hardcoded to `--surface-paper`/`--ink`'s literal values with a comment pointing back at `tokens.css` as the source of truth — the same kind of "kept in sync by hand" relationship Decision 13 already establishes between itself and this file.

## A pre-existing test-infrastructure gap, fixed in passing

`src/test/setup.ts` didn't call Testing Library's `cleanup()` between tests. `vite.config.ts` sets `globals: false`, and Testing Library's own auto-cleanup only registers itself when it finds a global `afterEach` — with `globals: false` there isn't one, so every render from an earlier test in the same file stayed mounted for the next. This was invisible until this part, because no earlier test file rendered more than one React tree per file (`App.test.tsx` has a single test). `Sheet.test.tsx`'s second test failed with "found multiple elements" against a leftover `<dialog>` from the first, which is what surfaced it. Fixed by adding an explicit `afterEach(() => cleanup())` to `setup.ts` — this fixes the gap for every test file in the project, not just this part's.

## Verification

```bash
pnpm verify   # typecheck + lint + format + 108 unit tests (11 files) + build — green
```

Manually verified in a real browser (Claude Code Browser pane), since none of this is meaningfully provable by unit tests alone:

| DoD requirement                                                                  | Where                                                                                                                                                                                                                        |
| -------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| gallery route renders every primitive, light and dark                            | `/gallery`; `ThemeToggle` cycled to dark, computed `--ink`/`--surface-paper` and the shell's rendered background/color confirmed to switch to the dark values (`#20261f`/`#f4ebe0`)                                          |
| keyboard tab order is correct through the shell                                  | Real `Tab` keypress in the browser: first stop is the skip link (moves on-screen to `top:16,left:16` on focus), matching the skip-link → header → nav → main order `AppShell`'s DOM produces                                 |
| shell renders correctly at 360px and 1920px                                      | Resized the Browser pane to both; confirmed no horizontal overflow (`document.documentElement.scrollWidth === window.innerWidth` at both), nav is `position: fixed` full-width at 360px and a static 224px sidebar at 1920px |
| no color hardcoded outside the token file                                        | Audited every new/touched CSS file and JS/JSON color literal (see "two pre-existing hardcoded colors" above); everything else styling-related reads `var(--token)`                                                           |
| every text token pair measured against AA, in both light and dark, recorded here | Table above, computed by `src/ui/contrast.ts`, asserted by `src/ui/contrast.test.ts`, rendered live at `/gallery`                                                                                                            |
| shell next to the installed icon reads as the same product                       | Same palette (Decision 13), same surfaces, and the two stray non-palette colors (`PwaPrompts` toast, manifest/meta theme colors) found and fixed above                                                                       |
