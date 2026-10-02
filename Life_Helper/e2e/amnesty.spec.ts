import { expect, test, type Page } from '@playwright/test'
import type { MutateInput } from '../src/db/ops.js'

// window.__lifeHelperDb is declared globally in triage.spec.ts.

const DAY_MS = 24 * 60 * 60 * 1000

function localMidnight(dayOffset: number): number {
  const d = new Date()
  return new Date(d.getFullYear(), d.getMonth(), d.getDate() + dayOffset).getTime()
}

function seedTask(
  id: string,
  title: string,
  fields: Record<string, number | null>,
  createdAt: number,
): MutateInput {
  return {
    writes: [
      {
        table: 'items',
        key: { id },
        fields: {
          kind: 'task',
          title,
          status: 'active',
          created_at: createdAt,
          updated_at: createdAt,
        },
      },
      { table: 'task_fields', key: { item_id: id }, fields },
    ],
  }
}

/**
 * Seeds through the real write path, then backdates the ops of the "old"
 * tasks: decay reads when a task was last touched from the ops log, and
 * mutate() stamps every op with the time it actually ran.
 */
async function seedWithOldTasks(page: Page): Promise<void> {
  const longAgo = Date.now() - 60 * DAY_MS
  await page.goto('/debug-db.html')
  await page.waitForFunction('window.__lifeHelperDb !== undefined')
  await page.evaluate(() => window.__lifeHelperDb.ready)
  const tasks = [
    seedTask('old-1', 'Old idea about a garden', {}, longAgo),
    seedTask(
      'old-2',
      'Old plan to paint the fence',
      { scheduled_for: localMidnight(-40) },
      longAgo,
    ),
    seedTask('fresh-1', 'Water the plants', { scheduled_for: localMidnight(0) }, Date.now()),
  ]
  for (const input of tasks) {
    await page.evaluate((i) => window.__lifeHelperDb.mutate(i), input)
  }
  for (const id of ['old-1', 'old-2']) {
    await page.evaluate(
      ([entity, time]) =>
        window.__lifeHelperDb.query('UPDATE ops SET created_at = ? WHERE entity_id = ?', [
          time,
          entity,
        ]),
      [id, longAgo] as const,
    )
  }
}

test('a fresh start from Today: confirm with the count, sweep, undo within 24 hours', async ({
  page,
}) => {
  await seedWithOldTasks(page)
  await page.goto('/')

  // The old planned task is on Today, carried over; the offer has no count.
  await expect(page.getByText('Old plan to paint the fence')).toBeVisible()
  const offer = page.getByRole('region', { name: 'Fresh start' })
  await expect(offer).toContainText('untouched for 30 days or more')
  await expect(offer).not.toContainText('2')

  await offer.getByRole('button', { name: 'Fresh start' }).click()
  const sheet = page.getByRole('dialog', { name: 'Fresh start' })
  await expect(sheet).toContainText('Move 2 tasks untouched for 30 days or more to Someday?')
  await sheet.getByRole('button', { name: 'Move 2 to Someday' }).click()

  await expect(page.getByText('Old plan to paint the fence')).toHaveCount(0)
  await expect(page.getByText('Water the plants')).toBeVisible()

  // The undo outlives the 10-second toast and a reload.
  await page.reload()
  const note = page.getByRole('region', { name: 'Fresh start' })
  await expect(note).toContainText('You can undo it until')
  await note.getByRole('button', { name: 'Undo fresh start' }).click()
  await expect(page.getByText('Old plan to paint the fence')).toBeVisible()
  // Exactly as before: eligible again, so the offer is back.
  await expect(
    page.getByRole('region', { name: 'Fresh start' }).getByRole('button', { name: 'Fresh start' }),
  ).toBeVisible()
})

test('someday: searchable, and one task can be brought back on its own', async ({ page }) => {
  await seedWithOldTasks(page)
  await page.goto('/')
  await page.getByRole('button', { name: 'Fresh start' }).click()
  await page
    .getByRole('dialog', { name: 'Fresh start' })
    .getByRole('button', { name: 'Move 2 to Someday' })
    .click()
  await expect(page.getByText('Old plan to paint the fence')).toHaveCount(0)

  await page.getByRole('link', { name: 'Someday' }).first().click()
  await expect(page.getByRole('heading', { name: 'Someday', level: 1 })).toBeVisible()
  await expect(page.getByRole('main').getByRole('listitem')).toHaveCount(2)

  await page.getByLabel('Search Someday').fill('gard')
  await expect(page.getByRole('main').getByRole('listitem')).toHaveCount(1)
  await expect(page.getByText('Old idea about a garden')).toBeVisible()
  await page.getByLabel('Search Someday').fill('')

  await page
    .getByRole('listitem', { name: 'Old plan to paint the fence' })
    .getByRole('button', { name: /^Bring back to today/ })
    .click()
  await expect(page.getByText('Brought back to today')).toBeVisible()
  await expect(page.getByRole('main').getByRole('listitem')).toHaveCount(1)

  await page.getByRole('link', { name: 'Today', exact: true }).click()
  await expect(page.getByText('Old plan to paint the fence')).toBeVisible()
})
