# Phase A, Part A1 — Repository, toolchain, and verification harness

Status: local scaffolding complete. Cloudflare Pages connection and account
creation are **not done** — see "Manual steps required" below; they need
the project owner's direct action and cannot be performed by an agent.

## What's in place

- Vite + React 19 + TypeScript `strict` (React 18 was the plan's baseline;
  React 19 is the current stable release as of this build and a fresh
  project has no reason to start on the older major — see "Deviations from
  the plan text" below)
- `vite-plugin-pwa` with a generated manifest, an icon set (192/512/maskable
  PNGs plus an Apple touch icon and favicon), `registerType: 'prompt'`, and
  an in-app install/update prompt (`src/pwa/PwaPrompts.tsx`)
- Vitest + `@testing-library/react` for unit/integration tests (`*.test.tsx`
  next to source, jsdom environment, V8 coverage)
- Playwright for e2e (`e2e/`), builds and serves the production bundle and
  drives it with Chromium
- ESLint (flat config, `typescript-eslint` `strictTypeChecked`) + Prettier,
  both wired into `pnpm verify`
- `pnpm verify` = `typecheck && lint && format:check && test:unit && build`
- `.nvmrc` (`26.4.0`) + `engines.node` + `packageManager` pin `pnpm@11.18.0`
  in `package.json`
- `.github/workflows/life-helper-verify.yml` at the monorepo root: runs
  `pnpm verify` on push, scoped to `Life_Helper/**` via a `paths` filter (this
  repo hosts other unrelated projects — see Decision 11's Actions-minutes
  budget), with a concurrency group that cancels superseded runs

## Repository layout note

This repo (`Nox-eturnus/Projects`) is a monorepo: `Life_Helper/` is one
folder among several unrelated projects (`Q_ALU/`, `QCNN-QKD/`), not its own
GitHub repository. That's consistent with how the other projects are
already organized here, and Cloudflare Pages supports building from a
subdirectory of a monorepo (set the Pages project's "root directory" to
`Life_Helper` — see manual steps below), so nothing in the plan requires a
dedicated repo.

## Deviations from the plan text

- **React 19, not React 18.** The plan's Decision section fixes the rest of
  the stack (Node, pnpm, TypeScript strict) but doesn't call out React 18
  as load-bearing for anything downstream; it reads as "current stable at
  time of writing." Starting a fresh project in mid-2026 on a superseded
  major would be the wrong call. Flagging this explicitly per the plan's
  own instruction to record any change before it's load-bearing elsewhere.
- **Icon generation is hand-rolled, not `@vite-pwa/assets-generator`.** That
  tool depends on `sharp`, whose prebuilt native binding fails to `dlopen`
  on this Windows + Node 26.4.0 combination (`ERR_DLOPEN_FAILED`), most
  likely because prebuilds haven't caught up to this Node major yet. Rather
  than chase a native-binary fix, `scripts/generate-icons.mjs` rasterizes
  the icon set by hand and encodes PNG using only Node's built-in `zlib` —
  zero native dependencies, deterministic, and in keeping with the project's
  own offline/zero-cost bias. Source vector kept at `assets/logo.svg` for
  reference; regenerate with `pnpm generate-icons`.
- **`vite-plugin-pwa`'s virtual module is aliased out under test.**
  `virtual:pwa-register/react` doesn't resolve inside Vitest's transform
  pipeline (`workbox-window` import fails, then a `file://` URL error).
  `vite.config.ts` swaps in a stub (`src/test/mocks/pwa-register-react.ts`)
  only when `mode === 'test'`; the real plugin and virtual module are used
  for `dev`/`build` unchanged.

## Manual steps required (cannot be done by an agent)

These are account-creation and OAuth/dashboard actions Claude will not
perform autonomously (account creation and granting third-party access are
both outside what an agent should do without you directly in the loop).
Recorded here so this part's Definition of Done can be tracked to completion:

1. **Create a Cloudflare account** (no credit card). Confirm no card is on
   file — this is the anchor of Decision 11's zero-cost constraint.
2. **Create a Google Cloud account/project** (no billing enabled) for the
   Phase C3 Calendar API — not needed until Phase C, but the plan asks
   this be confirmed in Part A1.
3. **Create a Cloudflare Pages project** connected to this GitHub repo,
   with:
   - root directory: `Life_Helper`
   - build command: `pnpm install && pnpm build`
   - build output directory: `dist`
4. **Confirm the Pages deploy is automatic and green** on push to `main`.
5. **Install the deployed PWA to an Android home screen** over the
   `*.pages.dev` HTTPS URL and confirm the install prompt appears and the
   app launches standalone.
6. Record every account's "no card on file" confirmation, and the measured
   Cloudflare Pages usage, in `docs/cost_ledger.md`.

Until these are done, Part A1's Definition of Done is not met — the local
toolchain (this document's first section) is necessary but not sufficient.

## Verification

```bash
node --version   # 26.4.0 (pinned in .nvmrc)
pnpm --version   # 11.18.0 (pinned in package.json#packageManager)
pnpm install
pnpm verify      # typecheck + lint + format check + unit tests + build — green
pnpm test:e2e    # Playwright e2e — green (builds + serves + drives Chromium)
```

Node 25+ no longer bundles Corepack, so "a clean clone on a machine with
only Node installed" needs one extra step before `pnpm` is on `PATH`:
`corepack enable` (or `npm install -g pnpm` if Corepack isn't available).
Either way, the resulting `pnpm` version should match
`package.json#packageManager`.

`pnpm verify` and `pnpm test:e2e` were both run clean locally on
2026-07-31. CI (`life-helper-verify.yml`) has not yet run — it fires on the
first push to a branch that touches `Life_Helper/**`.
