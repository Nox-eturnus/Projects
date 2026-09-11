import { expect, test, type Page } from '@playwright/test'
import type { MutateInput } from '../src/db/ops.js'

// window.__lifeHelperDb is declared globally in triage.spec.ts.

async function ready(page: Page): Promise<void> {
  await page.goto('/debug-db.html')
  await page.waitForFunction('window.__lifeHelperDb !== undefined')
  await page.evaluate(() => window.__lifeHelperDb.ready)
}

function seedTask(id: string, title: string, scheduledFor: number | null): MutateInput {
  return {
    writes: [
      {
        table: 'items',
        key: { id },
        fields: {
          kind: 'task',
          title,
          status: 'active',
          created_at: 1_000 + Number(id.replace(/\D/g, '')),
          updated_at: 1_000,
        },
      },
      { table: 'task_fields', key: { item_id: id }, fields: { scheduled_for: scheduledFor } },
    ],
  }
}

async function seed(page: Page, tasks: MutateInput[]): Promise<void> {
  await ready(page)
  for (const input of tasks) {
    await page.evaluate((i) => window.__lifeHelperDb.mutate(i), input)
  }
}

function localMidnight(dayOffset: number): number {
  const d = new Date()
  return new Date(d.getFullYear(), d.getMonth(), d.getDate() + dayOffset).getTime()
}

function localKey(dayOffset: number): string {
  const d = new Date(localMidnight(dayOffset))
  return `${d.getFullYear().toString()}-${(d.getMonth() + 1).toString().padStart(2, '0')}-${d
    .getDate()
    .toString()
    .padStart(2, '0')}`
}

const topThree = (page: Page) => page.getByRole('region', { name: 'Your three' })

test('skipping the shutdown still gives a proposal; accepting it persists across a reload, scoped to today', async ({
  page,
}) => {
  await seed(page, [
    seedTask('t1', 'Water the plants', localMidnight(0)),
    seedTask('t2', 'Reply to Sam', localMidnight(0)),
    seedTask('t3', 'Book dentist', localMidnight(-1)),
    seedTask('t4', 'Tidy desk', localMidnight(0)),
  ])

  await page.goto('/')
  const proposal = page.getByRole('region', { name: 'Three to start with' })
  await expect(proposal).toBeVisible()
  await expect(proposal.getByText('Book dentist')).toBeVisible() // carried over leads
  await page.getByRole('button', { name: 'Accept these three' }).click()
  await expect(topThree(page).getByRole('checkbox')).toHaveCount(3)

  await page.reload()
  await expect(topThree(page).getByRole('checkbox')).toHaveCount(3)
  await expect(topThree(page).getByText('Book dentist')).toBeVisible()

  // Tomorrow, today's commitment is history: Today is back to proposing.
  await page.clock.install({ time: localMidnight(1) + 9 * 60 * 60 * 1000 })
  await page.reload()
  await expect(page.getByRole('region', { name: 'Three to start with' })).toBeVisible()
  await expect(topThree(page)).toHaveCount(0)
})

test('completing all three shows a finish state instead of surfacing more work', async ({
  page,
}) => {
  await seed(page, [
    seedTask('t1', 'One', localMidnight(0)),
    seedTask('t2', 'Two', localMidnight(0)),
    seedTask('t3', 'Three', localMidnight(0)),
    seedTask('t4', 'Also on today', localMidnight(0)),
  ])

  await page.goto('/')
  await page.getByRole('button', { name: 'Accept these three' }).click()
  for (const name of ['One', 'Two', 'Three']) {
    await topThree(page).getByRole('checkbox', { name }).check()
  }

  await expect(page.getByText("That's all three. The rest of the day is yours.")).toBeVisible()
  await expect(page.getByText('Also on today')).toHaveCount(0)
  await page.getByRole('button', { name: 'Show the rest of today' }).click()
  await expect(page.getByText('Also on today')).toBeVisible()
})

test('the evening shutdown completes in under 60 seconds and sets tomorrow’s three', async ({
  page,
}) => {
  await seed(page, [
    seedTask('t1', 'Finish report', localMidnight(0)),
    seedTask('t2', 'Call the bank', localMidnight(0)),
    seedTask('t3', 'Gym', localMidnight(1)),
    seedTask('t4', 'Groceries', localMidnight(1)),
    seedTask('t5', 'Read chapter 4', localMidnight(1)),
    seedTask('t6', 'Plan trip', null),
  ])

  await page.goto('/shutdown')
  const started = Date.now()

  // Review: one of today's two was actually done.
  await page.getByRole('checkbox', { name: 'Finish report' }).check()
  await page.getByRole('button', { name: /Next: tomorrow/ }).click()
  // Pick: the preselection is fine as it is.
  await expect(page.getByRole('button', { pressed: true })).toHaveCount(3)
  await page.getByRole('button', { name: "Set tomorrow's three" }).click()
  await expect(page.getByRole('heading', { name: 'Tomorrow is set.' })).toBeVisible()

  const elapsedMs = Date.now() - started
  expect(elapsedMs).toBeLessThan(60_000)

  // Durable, and on the right dates: tomorrow has the three, tonight has the shutdown.
  await ready(page)
  const plans = (await page.evaluate(
    ([today, tomorrow]) =>
      window.__lifeHelperDb.query(
        'SELECT day, top1_id, top2_id, top3_id, committed_via, shutdown_completed_at FROM day_plans WHERE day IN (?, ?) ORDER BY day',
        [today, tomorrow],
      ),
    [localKey(0), localKey(1)],
  )) as {
    day: string
    top1_id: string | null
    committed_via: string | null
    shutdown_completed_at: number | null
  }[]
  expect(plans).toHaveLength(2)
  expect(plans[0]).toMatchObject({ day: localKey(0) })
  expect(plans[0].shutdown_completed_at).not.toBeNull()
  expect(plans[1]).toMatchObject({ day: localKey(1), top1_id: 't2', committed_via: 'shutdown' })

  // And tomorrow morning, Today opens on exactly those three.
  await page.clock.install({ time: localMidnight(1) + 8 * 60 * 60 * 1000 })
  await page.goto('/')
  await expect(topThree(page).getByRole('checkbox')).toHaveCount(3)
  await expect(topThree(page).getByText('Call the bank')).toBeVisible()
})
