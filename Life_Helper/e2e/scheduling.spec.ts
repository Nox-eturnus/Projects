import { expect, test, type Page } from '@playwright/test'
import type { MutateInput } from '../src/db/ops.js'

// window.__lifeHelperDb is declared globally in triage.spec.ts.

async function ready(page: Page): Promise<void> {
  await page.goto('/debug-db.html')
  await page.waitForFunction('window.__lifeHelperDb !== undefined')
  await page.evaluate(() => window.__lifeHelperDb.ready)
}

function seedInboxTask(
  id: string,
  title: string,
  createdAt: number,
  deferUntil: number | null,
): MutateInput {
  return {
    writes: [
      {
        table: 'items',
        key: { id },
        fields: {
          kind: 'task',
          title,
          status: 'inbox',
          created_at: createdAt,
          updated_at: createdAt,
        },
      },
      { table: 'task_fields', key: { item_id: id }, fields: { defer_until: deferUntil } },
    ],
  }
}

test('a task deferred to tomorrow is absent from every task view, then appears at midnight without a reload', async ({
  page,
}) => {
  // The page's clock is pinned to one minute before local midnight, so the
  // rollover can be driven deterministically rather than waited for. The
  // browser shares this machine's timezone, so "local" agrees on both sides.
  const today = new Date()
  const oneMinuteToMidnight = new Date(
    today.getFullYear(),
    today.getMonth(),
    today.getDate(),
    23,
    59,
  ).getTime()
  const tomorrow = new Date(today.getFullYear(), today.getMonth(), today.getDate() + 1).getTime()

  await ready(page)
  await page.evaluate(
    (input) => window.__lifeHelperDb.mutate(input),
    seedInboxTask('visible', 'Visible today', oneMinuteToMidnight - 60_000, null),
  )
  await page.evaluate(
    (input) => window.__lifeHelperDb.mutate(input),
    seedInboxTask('deferred', 'Deferred to tomorrow', oneMinuteToMidnight - 30_000, tomorrow),
  )

  await page.clock.install({ time: oneMinuteToMidnight })

  // Capture's "Recently captured" list is a task view too.
  await page.goto('/capture')
  await expect(page.getByText('Visible today')).toBeVisible()
  await expect(page.getByText('Deferred to tomorrow')).toHaveCount(0)

  await page.goto('/inbox')
  await expect(page.getByText('Visible today')).toBeVisible()
  await expect(page.getByText('Deferred to tomorrow')).toHaveCount(0)

  await page.clock.runFor(60_000)

  await expect(page.getByText('Deferred to tomorrow')).toBeVisible()
  await expect(page.getByText('Visible today')).toBeVisible()
})
