# Life Helper

A single-user, local-first, offline-capable personal operating system: frictionless capture, a Today dashboard, routines and streaks, projects and retainers, a personal CRM, a notes library.

See [`life_helper_implementation_plan_v1.md`](./life_helper_implementation_plan_v1.md) for the full design and phase plan, and [`docs/`](./docs) for phase-by-phase implementation notes.

## Toolchain

- Node.js, pinned via `.nvmrc` and `engines` in `package.json`
- pnpm, pinned via `packageManager` in `package.json`
- TypeScript in `strict` mode
- Vite + React 19 + `vite-plugin-pwa`
- Vitest (unit/integration) + Playwright (e2e)
- ESLint + Prettier

## Commands

```bash
pnpm install       # install dependencies
pnpm dev           # start the dev server
pnpm verify        # typecheck + lint + format check + unit tests + build
pnpm test:unit     # unit/integration tests only
pnpm test:e2e      # Playwright end-to-end tests
pnpm build         # production build
```

No phase of the implementation plan is considered complete while `pnpm verify` is failing.
