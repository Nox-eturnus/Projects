import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  reporter: 'html',
  use: {
    baseURL: 'http://localhost:4173',
    trace: 'on-first-retry',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: {
    // LIFE_HELPER_INCLUDE_DEBUG_HARNESS pulls debug-db.html into this
    // build (see vite.config.ts) so db.spec.ts can drive it. The real
    // Cloudflare Pages deploy runs a plain `pnpm build` and never sets
    // this, so the debug harness never ships in production.
    command: 'cross-env LIFE_HELPER_INCLUDE_DEBUG_HARNESS=1 pnpm build && pnpm preview --port 4173',
    url: 'http://localhost:4173',
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
})
