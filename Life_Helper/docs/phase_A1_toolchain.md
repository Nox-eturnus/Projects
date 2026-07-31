# Phase A, Part A1 — Repository, toolchain, and verification harness

Status: **done, with one recorded deviation.** Cloudflare (hosting, account,
Pages project, Android install) is fully confirmed. Google Cloud account
creation is **blocked** — it requires a billing account (a card) even for
its nominally free tier, which Decision 11 disqualifies outright. This is
deferred under Decision 12 rather than treated as an open item — see
"Google Cloud: blocked" below.

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
- Playwright for e2e (`e2e/`), builds and serves the production bundle,
  drives it with Chromium, and asserts the service worker actually
  registers and the manifest resolves with the expected icon set
- ESLint (flat config, `typescript-eslint` `strictTypeChecked` for TS,
  `js.configs.recommended` for plain JS/scripts) + Prettier, both wired
  into `pnpm verify`
- `pnpm verify` = `typecheck && lint && format:check && test:unit && build`
- `.nvmrc` (`26.4.0`) + `engines.node` + `packageManager` pin `pnpm@11.18.0`
  in `package.json`
- `.gitattributes` (`* text=auto eol=lf`) — see "Deviations" below; without
  this, a fresh clone on Windows with the common `core.autocrlf=true`
  setting fails `prettier --check` (and therefore `pnpm verify`) on a clean
  checkout, which directly undermines this part's own DoD
- `.github/workflows/life-helper-verify.yml` at the monorepo root: runs
  `pnpm verify` on push, scoped to `Life_Helper/**` via a `paths` filter
  (this repo hosts other unrelated projects — see Decision 11's
  Actions-minutes budget), with a concurrency group that cancels
  superseded runs
- **Deployed and live** at `https://life-helper.pages.dev/` via Cloudflare
  Pages, connected to this repo, root directory `Life_Helper`, building
  `pnpm install && pnpm build` into `dist`
- **Installed on Android** — confirmed working (install prompt appeared,
  launches standalone)

## Repository layout note

This repo (`Nox-eturnus/Projects`) is a monorepo: `Life_Helper/` is one
folder among several unrelated projects (`Q_ALU/`, `QCNN-QKD/`), not its own
GitHub repository. That's consistent with how the other projects are
already organized here, and Cloudflare Pages supports building from a
subdirectory of a monorepo (root directory set to `Life_Helper`), so nothing
in the plan requires a dedicated repo.

## Deviations from the plan text

- **React 19, not React 18.** The plan's Decision section fixes the rest of
  the stack (Node, pnpm, TypeScript strict) but doesn't call out React 18
  as load-bearing for anything downstream; it reads as "current stable at
  time of writing." Starting a fresh project in mid-2026 on a superseded
  major would be the wrong call.
- **Icon generation is hand-rolled, not `@vite-pwa/assets-generator`.** That
  tool depends on `sharp`, whose prebuilt native binding fails to `dlopen`
  on this Windows + Node 26.4.0 combination (`ERR_DLOPEN_FAILED`). Rather
  than chase a native-binary fix, `scripts/generate-icons.mjs` rasterizes
  the icon set by hand and encodes PNG using only Node's built-in `zlib` —
  zero native dependencies, deterministic, and in keeping with the
  project's own offline/zero-cost bias. Source vector kept at
  `assets/logo.svg` for reference; regenerate with `pnpm generate-icons`.
- **`vite-plugin-pwa`'s virtual module is aliased out under test.**
  `virtual:pwa-register/react` doesn't resolve inside Vitest's transform
  pipeline (`workbox-window` import fails, then a `file://` URL error).
  `vite.config.ts` swaps in a stub (`src/test/mocks/pwa-register-react.ts`)
  only when `mode === 'test'`; the real plugin and virtual module are used
  for `dev`/`build` unchanged, and the e2e suite covers the real path.
- **`.gitattributes` added after the fact.** A clean clone on Windows with
  `core.autocrlf=true` (a very common default) checks tracked files out
  with CRLF line endings, which then fails `prettier --check` even though
  the committed content is byte-identical modulo line endings. This was
  only discovered while re-verifying the toolchain after merge, not during
  the original build — worth noting because it means the same class of bug
  could resurface for any file added without going through `pnpm format`
  first on a Windows machine with autocrlf on.
- **Cloudflare Pages, via the Git-connected wizard, not the newer unified
  "Workers" flow.** Cloudflare has been folding classic Pages into
  Workers-with-static-assets; the default "Create a Worker" flow expects a
  `wrangler.jsonc` and doesn't expose a root-directory field up front. We
  used the still-available Pages-specific "Connect to Git" wizard instead,
  which matches this document's original instructions exactly (root
  directory / build command / build output directory as plain form
  fields) and needs no `wrangler.jsonc` in the repo. If Cloudflare
  eventually removes the Pages wizard entirely, migrating to Workers
  static assets is documented at
  <https://developers.cloudflare.com/workers/static-assets/migration-guides/migrate-from-pages/>
  and stays zero-cost either way (static asset requests are free on
  Workers too).

## Google Cloud: blocked

Google Cloud project creation requires linking a billing account (a credit
card) before you can do anything with it — including using APIs that are
themselves free, like Google Calendar's. The "free trial" still demands a
card up front. This directly conflicts with Decision 11 ("No credit card on
file anywhere... If a service asks for a card to proceed, that service is
disqualified") and was confirmed by the project owner directly, not
assumed.

This is handled as a deferral, not a blocker on Part A1, because:

- Decision 12 anticipates exactly this: "If Google Calendar OAuth becomes a
  blocker, ship Phase C without capacity computation and treat calendar as
  a Phase D-parallel task. Do not let a third-party API block the first
  pillar."
- Nothing in Phase A, Phase B, or most of Phase C depends on Google Cloud.
  Only Part C3 (free-capacity display) and Part G3 (pre-meeting brief) do.
- It's recorded in `docs/cost_ledger.md` (Account confirmations table) so
  it isn't silently forgotten, and it's the thing to revisit first when
  Part C3 starts.

If a card-free path to a Google Cloud project ever becomes available, or a
different calendar integration approach is found, that supersedes this
note. Until then, Part C3 should be scoped and built without calendar
capacity computation, per the plan's own stop/pivot rule.

## Manual steps (status)

1. ✅ **Cloudflare account created**, no credit card on file (confirmed by
   the project owner directly).
2. ❌ **Google Cloud account/project** — blocked, see above. Not required
   for A1's own DoD; required starting Part C3.
3. ✅ **Cloudflare Pages project created**, connected to this GitHub repo:
   root directory `Life_Helper`, build command `pnpm install && pnpm build`,
   build output directory `dist`.
4. ✅ **Pages deploy is automatic and green** on push to `main` — confirmed
   live at `https://life-helper.pages.dev/`; HTTP 200 verified directly on
   `/`, `/manifest.webmanifest`, `/sw.js`, and an icon path, each with the
   correct content type.
5. ✅ **Installed on Android home screen** over the `*.pages.dev` HTTPS
   URL — install prompt appeared, app launches standalone (confirmed by
   the project owner directly).
6. ✅ Account confirmations and measured Cloudflare/GitHub usage recorded
   in `docs/cost_ledger.md`; Google Cloud recorded as blocked there too.

Part A1's Definition of Done is met for everything Cloudflare-dependent.
The one open item (Google Cloud / Calendar) is explicitly deferred to
Part C3 under Decision 12, not silently dropped.

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
2026-07-31, from a checkout with `.gitattributes` in effect (see
Deviations). CI (`life-helper-verify.yml`) has run twice on push to
`main`/the feature branch, both green.
