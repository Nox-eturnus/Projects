import { chromium, expect, test, type Page } from '@playwright/test'
import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import type { MutateInput } from '../src/db/ops.js'

declare global {
  interface Window {
    // Typed as always-present: every .evaluate() callback in this file
    // only ever runs after ready() below has resolved, at which point
    // debugHarness.ts has genuinely set this. The "not set yet" window
    // before that is handled by the untyped, string-form waitForFunction
    // in ready() instead, which TypeScript never sees.
    __lifeHelperDb: {
      mutate: (input: MutateInput) => Promise<unknown>
      query: (sql: string, params?: unknown[]) => Promise<unknown>
      getDeviceId: () => Promise<string>
      ready: Promise<void>
    }
  }
}

async function ready(page: Page): Promise<void> {
  await page.goto('/debug-db.html')
  await page.waitForFunction('window.__lifeHelperDb !== undefined')
  await page.evaluate(() => window.__lifeHelperDb.ready)
}

function insertTaskWrite(id: string, title: string): MutateInput {
  return {
    writes: [
      {
        table: 'items',
        key: { id },
        fields: { kind: 'task', title, created_at: 1, updated_at: 1 },
      },
    ],
  }
}

test('data survives a full page reload (proxy for a hard restart)', async ({ page }) => {
  await ready(page)
  await page.evaluate(
    (input) => window.__lifeHelperDb.mutate(input),
    insertTaskWrite('reload-task', 'Survives reload'),
  )

  await page.reload()
  await page.waitForFunction('window.__lifeHelperDb !== undefined')
  await page.evaluate(() => window.__lifeHelperDb.ready)

  const rows = await page.evaluate(() => window.__lifeHelperDb.query('SELECT title FROM items'))
  expect(rows).toEqual([{ title: 'Survives reload' }])
})

test('data survives a full browser process restart against the same on-disk profile (proxy for an OS restart)', async ({
  baseURL,
}) => {
  // OPFS lives inside the browser's on-disk profile, not in cookies or
  // localStorage — storageState() doesn't capture it. A real persistent
  // profile directory, closed and relaunched, is the only way to exercise
  // this rather than just reloading a page that never actually restarted.
  const userDataDir = mkdtempSync(join(tmpdir(), 'life-helper-opfs-'))
  try {
    const context1 = await chromium.launchPersistentContext(userDataDir, { baseURL })
    try {
      const page1 = await context1.newPage()
      await ready(page1)
      await page1.evaluate(
        (input) => window.__lifeHelperDb.mutate(input),
        insertTaskWrite('profile-task', 'Survives an OS restart'),
      )
    } finally {
      await context1.close() // fully tears down this browser process
    }

    const context2 = await chromium.launchPersistentContext(userDataDir, { baseURL })
    try {
      const page2 = await context2.newPage()
      await ready(page2)
      const rows = await page2.evaluate(() =>
        window.__lifeHelperDb.query('SELECT title FROM items'),
      )
      expect(rows).toEqual([{ title: 'Survives an OS restart' }])
    } finally {
      await context2.close()
    }
  } finally {
    rmSync(userDataDir, { recursive: true, force: true })
  }
})

test('two tabs share one database with no corruption, and stay reactive to each other', async ({
  context,
}) => {
  const tab1 = await context.newPage()
  const tab2 = await context.newPage()
  await ready(tab1)
  await ready(tab2)

  const [deviceId1, deviceId2] = await Promise.all([
    tab1.evaluate(() => window.__lifeHelperDb.getDeviceId()),
    tab2.evaluate(() => window.__lifeHelperDb.getDeviceId()),
  ])
  // Same underlying leader worker/database, not two independent ones.
  expect(deviceId1).toBe(deviceId2)

  await tab1.evaluate(
    (input) => window.__lifeHelperDb.mutate(input),
    insertTaskWrite('t1', 'From tab 1'),
  )
  await tab2.evaluate(
    (input) => window.__lifeHelperDb.mutate(input),
    insertTaskWrite('t2', 'From tab 2'),
  )

  const [rows1, rows2] = await Promise.all([
    tab1.evaluate(() => window.__lifeHelperDb.query('SELECT id FROM items ORDER BY id')),
    tab2.evaluate(() => window.__lifeHelperDb.query('SELECT id FROM items ORDER BY id')),
  ])
  expect(rows1).toEqual([{ id: 't1' }, { id: 't2' }])
  expect(rows2).toEqual([{ id: 't1' }, { id: 't2' }])

  // Cross-tab reactivity: tab1's subscribe() callback renders the changed
  // table list into #out whenever any tab mutates (see debugHarness.ts).
  await expect(tab1.locator('#out')).toContainText('changed: items')
})

test('a leader tab closing promotes a follower, and writes keep working', async ({ context }) => {
  const tab1 = await context.newPage()
  await ready(tab1)
  await tab1.evaluate(
    (input) => window.__lifeHelperDb.mutate(input),
    insertTaskWrite('before', 'Before failover'),
  )

  const tab2 = await context.newPage()
  await ready(tab2)

  await tab1.close() // the leader; tab2 must be promoted

  await tab2.evaluate(
    (input) => window.__lifeHelperDb.mutate(input),
    insertTaskWrite('after', 'After failover'),
  )
  const rows = await tab2.evaluate(() =>
    window.__lifeHelperDb.query('SELECT id FROM items ORDER BY id'),
  )
  expect(rows).toEqual([{ id: 'after' }, { id: 'before' }])
})
