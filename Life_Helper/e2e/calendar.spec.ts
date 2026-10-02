import { createServer, type Server } from 'node:http'
import type { AddressInfo } from 'node:net'
import { expect, test, type Page } from '@playwright/test'
import type { MutateInput } from '../src/db/ops.js'
import { handle, type Env } from '../edge/src/index.js'

// window.__lifeHelperDb is declared globally in triage.spec.ts.

/**
 * Part C3 end to end, with the real edge Worker code in the loop: each
 * test serves `handle()` from edge/src/index.ts over real HTTP on its own
 * 127.0.0.1 port, and only Google itself is faked. The app (on
 * localhost:4173) calling it is a genuinely cross-origin request, so the
 * browser enforces CORS exactly as it will against the deployed Worker —
 * an earlier version routed requests through page.route() instead, and a
 * mutation check showed Chromium doesn't apply CORS to fulfilled routes,
 * so a broken ALLOWED_ORIGINS passed. The device key, error mapping, the
 * client cache, and Today's rendering are all exercised for real too.
 */
const DEVICE_KEY = 'e2e-device-key-'.padEnd(43, 'x')
const HOUR = 60 * 60 * 1000

function localMidnight(dayOffset = 0): number {
  const d = new Date()
  return new Date(d.getFullYear(), d.getMonth(), d.getDate() + dayOffset).getTime()
}

type GoogleMode = 'ok' | 'revoked'

interface FakeEdge {
  reachable: boolean
  google: GoogleMode
  requests: number
  url: string
  server: Server
}

async function startEdge(): Promise<FakeEdge> {
  const edge = { reachable: true, google: 'ok', requests: 0, url: '' } as FakeEdge
  const env: Env = {
    GOOGLE_CLIENT_ID: 'e2e-client.apps.googleusercontent.com',
    GOOGLE_CLIENT_SECRET: 'e2e-secret',
    GOOGLE_REFRESH_TOKEN: 'e2e-refresh',
    DEVICE_TOKEN: DEVICE_KEY,
    ALLOWED_ORIGINS: 'http://localhost:4173',
  }
  const fakeGoogle: typeof fetch = (input) => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
    if (url.startsWith('https://oauth2.googleapis.com/token')) {
      return Promise.resolve(
        edge.google === 'revoked'
          ? Response.json({ error: 'invalid_grant' }, { status: 400 })
          : Response.json({
              access_token: 'e2e-access',
              scope: 'https://www.googleapis.com/auth/calendar.readonly',
            }),
      )
    }
    const today = localMidnight()
    return Promise.resolve(
      Response.json({
        items: [
          {
            id: 'standup',
            summary: 'Team standup',
            start: { dateTime: new Date(today + 9 * HOUR).toISOString() },
            end: { dateTime: new Date(today + 9.5 * HOUR).toISOString() },
          },
          {
            id: 'dentist',
            summary: 'Dentist',
            start: { dateTime: new Date(today + 16 * HOUR).toISOString() },
            end: { dateTime: new Date(today + 17 * HOUR).toISOString() },
          },
        ],
      }),
    )
  }

  edge.server = createServer((incoming, outgoing) => {
    if (!edge.reachable) {
      incoming.socket.destroy()
      return
    }
    edge.requests += 1
    const headers = new Headers()
    for (const [name, value] of Object.entries(incoming.headers)) {
      if (typeof value === 'string') headers.set(name, value)
    }
    void handle(
      new Request(`${edge.url}${incoming.url ?? '/'}`, { method: incoming.method, headers }),
      env,
      fakeGoogle,
    ).then(async (response) => {
      outgoing.writeHead(response.status, Object.fromEntries(response.headers))
      outgoing.end(response.status === 204 ? undefined : await response.text())
    })
  })
  await new Promise<void>((resolve) => edge.server.listen(0, '127.0.0.1', resolve))
  edge.url = `http://127.0.0.1:${String((edge.server.address() as AddressInfo).port)}`
  return edge
}

let edge: FakeEdge

test.beforeEach(async () => {
  edge = await startEdge()
})

test.afterEach(async () => {
  edge.server.closeAllConnections()
  await new Promise((resolve) => edge.server.close(resolve))
})

async function seedTask(page: Page, title: string, estimateMin: number): Promise<void> {
  await page.goto('/debug-db.html')
  await page.waitForFunction('window.__lifeHelperDb !== undefined')
  await page.evaluate(() => window.__lifeHelperDb.ready)
  const input: MutateInput = {
    writes: [
      {
        table: 'items',
        key: { id: 'task-1' },
        fields: { kind: 'task', title, status: 'active', created_at: 1, updated_at: 1 },
      },
      {
        table: 'task_fields',
        key: { item_id: 'task-1' },
        fields: { scheduled_for: localMidnight(), estimate_min: estimateMin },
      },
    ],
  }
  await page.evaluate((i) => window.__lifeHelperDb.mutate(i), input)
}

async function connect(page: Page): Promise<void> {
  await page.goto('/settings')
  await page.getByLabel('Worker address').fill(edge.url)
  await page.getByLabel('Device key').fill(DEVICE_KEY)
  await page.getByRole('button', { name: 'Connect' }).click()
  await expect(page.getByText(/^Working\. Last updated/)).toBeVisible()
}

const calendar = (page: Page) => page.getByRole('region', { name: 'Calendar' })

test('events render on Today, with free time worked out around them', async ({ page }) => {
  await seedTask(page, 'Write the report', 90)
  await connect(page)

  await page.getByRole('link', { name: 'Today', exact: true }).click()
  await expect(calendar(page).getByText('Team standup')).toBeVisible()
  await expect(calendar(page).getByText('Dentist')).toBeVisible()
  await expect(calendar(page).getByText(/^Updated/)).toBeVisible()
  await expect(page.getByText(/your three need about/)).toContainText('1h 30m')
})

test('Today renders fully offline from the cache, with a visible staleness indicator', async ({
  page,
  context,
}) => {
  await connect(page)
  await page.goto('/')
  await expect(calendar(page).getByText('Team standup')).toBeVisible()
  // A second navigation, so the service worker controls the page and the
  // app itself is served from its precache once the network is gone.
  await page.goto('/')
  await expect(calendar(page).getByText('Team standup')).toBeVisible()

  edge.reachable = false
  await context.setOffline(true)
  await page.reload()

  await expect(calendar(page).getByText('Team standup')).toBeVisible()
  await calendar(page).getByRole('button', { name: 'Refresh' }).click()
  await expect(calendar(page).getByText(/^Offline — calendar as of/)).toBeVisible()
  await expect(calendar(page).getByText('Dentist')).toBeVisible()

  await context.setOffline(false)
})

test('a revoked Google grant produces a clear reconnect prompt, not a crash', async ({ page }) => {
  await seedTask(page, 'Write the report', 30)
  await connect(page)
  await page.getByRole('link', { name: 'Today', exact: true }).click()
  await expect(calendar(page).getByText('Team standup')).toBeVisible()

  edge.google = 'revoked'
  await calendar(page).getByRole('button', { name: 'Refresh' }).click()

  await expect(page.getByText(/Google Calendar needs reconnecting/)).toBeVisible()
  // Everything else still works: the last known events, and the tasks.
  await expect(calendar(page).getByText('Team standup')).toBeVisible()
  await expect(page.getByText('Write the report')).toBeVisible()
})

test('a wrong device key is refused by the Worker, and Settings says so', async ({ page }) => {
  await page.goto('/settings')
  await page.getByLabel('Worker address').fill(edge.url)
  await page.getByLabel('Device key').fill('not-the-key'.padEnd(43, 'y'))
  await page.getByRole('button', { name: 'Connect' }).click()
  await expect(page.getByText("The Worker didn't accept this device key.")).toBeVisible()
})
