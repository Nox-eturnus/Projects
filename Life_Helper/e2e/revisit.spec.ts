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
  createdAt = 1_000,
): MutateInput {
  return {
    writes: [
      {
        table: 'items',
        key: { id },
        fields: { kind: 'task', title, status: 'active', created_at: createdAt, updated_at: 1_000 },
      },
      { table: 'task_fields', key: { item_id: id }, fields },
    ],
  }
}

async function seed(page: Page, tasks: MutateInput[]): Promise<void> {
  await page.goto('/debug-db.html')
  await page.waitForFunction('window.__lifeHelperDb !== undefined')
  await page.evaluate(() => window.__lifeHelperDb.ready)
  for (const input of tasks) {
    await page.evaluate((i) => window.__lifeHelperDb.mutate(i), input)
  }
}

function seedSlipping(page: Page): Promise<void> {
  return seed(page, [
    seedTask('t1', 'Renew passport', {
      touch_count: 4,
      last_touched_at: Date.now() - DAY_MS,
      scheduled_for: localMidnight(0),
    }),
    seedTask('t2', 'Sort out the garage', {
      scheduled_for: localMidnight(-12),
    }),
    seedTask('t3', 'Call the insurer', {
      touch_count: 1,
      last_touched_at: Date.now() - 3 * DAY_MS,
    }),
    seedTask('t4', 'Water the plants', { scheduled_for: localMidnight(0) }),
  ])
}

const card = (page: Page, title: string) => page.getByRole('listitem', { name: title })

test('Revisit ranks by moves, then age, and do it now puts a task in today’s three', async ({
  page,
}) => {
  await seedSlipping(page)
  await page.goto('/revisit')

  await expect(page.getByRole('heading', { name: 'Revisit', level: 1 })).toBeVisible()
  const titles = page.getByRole('main').getByRole('listitem')
  await expect(titles).toHaveCount(3) // "Water the plants" is just today's task
  await expect(titles.nth(0)).toContainText('Renew passport')
  await expect(titles.nth(1)).toContainText('Call the insurer')
  await expect(titles.nth(2)).toContainText('Sort out the garage')

  await card(page, 'Call the insurer').getByRole('button', { name: 'Do it now' }).click()
  await expect(page.getByText("Added to today's three")).toBeVisible()
  await expect(card(page, 'Call the insurer')).toHaveCount(0)

  await page.getByRole('link', { name: 'Today' }).click()
  const three = page.getByRole('region', { name: 'Your three' })
  await expect(three.getByText('Call the insurer')).toBeVisible()

  // Persisted, not just on screen.
  await page.reload()
  await expect(
    page.getByRole('region', { name: 'Your three' }).getByText('Call the insurer'),
  ).toBeVisible()
})

test('break it down: the steps land on today, the original leaves; undo puts it back', async ({
  page,
}) => {
  await seedSlipping(page)
  await page.goto('/revisit')

  await card(page, 'Sort out the garage').getByRole('button', { name: 'Break it down' }).click()
  const sheet = page.getByRole('dialog', { name: 'Break it down' })
  await sheet.getByLabel('Step 1').fill('Clear the shelves')
  await sheet.getByLabel('Step 2').fill('Take boxes to the tip')
  await sheet.getByRole('button', { name: 'Break it down' }).click()

  await expect(page.getByText('Split into 2 steps')).toBeVisible()
  await expect(card(page, 'Sort out the garage')).toHaveCount(0)

  await page.getByRole('button', { name: 'Undo' }).click()
  await expect(card(page, 'Sort out the garage')).toBeVisible()

  // Do it again and keep it this time: Today shows the steps, not the original.
  await card(page, 'Sort out the garage').getByRole('button', { name: 'Break it down' }).click()
  await sheet.getByLabel('Step 1').fill('Clear the shelves')
  await sheet.getByRole('button', { name: 'Break it down' }).click()
  await expect(page.getByText('Replaced with 1 step')).toBeVisible()

  await page.getByRole('link', { name: 'Today' }).click()
  await expect(page.getByText('Clear the shelves')).toBeVisible()
  await expect(page.getByText('Sort out the garage')).toHaveCount(0)
})

test('let it go: someday takes it out of Revisit and Today; undo brings it back', async ({
  page,
}) => {
  await seedSlipping(page)
  await page.goto('/revisit')

  await card(page, 'Renew passport').getByRole('button', { name: 'Let it go' }).click()
  await page
    .getByRole('dialog', { name: 'Let it go' })
    .getByRole('button', { name: 'Move to someday' })
    .click()
  await expect(page.getByText('Moved to someday')).toBeVisible()
  await expect(card(page, 'Renew passport')).toHaveCount(0)

  await page.getByRole('button', { name: 'Undo' }).click()
  await expect(card(page, 'Renew passport')).toBeVisible()

  await card(page, 'Renew passport').getByRole('button', { name: 'Let it go' }).click()
  await page
    .getByRole('dialog', { name: 'Let it go' })
    .getByRole('button', { name: 'Move to someday' })
    .click()
  await page.getByRole('link', { name: 'Today' }).click()
  await expect(page.getByRole('heading', { name: 'Today', level: 1 })).toBeVisible()
  await expect(page.getByText('Renew passport')).toHaveCount(0)
})

test('nothing slipping: an encouraging empty state, not an alarm', async ({ page }) => {
  await seed(page, [seedTask('t1', 'Water the plants', { scheduled_for: localMidnight(0) })])
  await page.goto('/revisit')
  await expect(page.getByText(/Nothing needs a second look/)).toBeVisible()
  await page.getByRole('button', { name: 'Go to Today' }).click()
  await expect(page.getByRole('heading', { name: 'Today', level: 1 })).toBeVisible()
})
