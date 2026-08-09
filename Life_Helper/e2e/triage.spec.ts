import { expect, test, type Page } from '@playwright/test'
import type { MutateInput } from '../src/db/ops.js'

declare global {
  interface Window {
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

function seedInboxTask(id: string, title: string, createdAt: number): MutateInput {
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
      { table: 'task_fields', key: { item_id: id }, fields: {} },
    ],
  }
}

function itemsLeftText(n: number): string {
  return `${n.toString()} ${n === 1 ? 'item' : 'items'} left`
}

test('an inbox of 20 items can be fully triaged in under 90 seconds using only the keyboard', async ({
  page,
}) => {
  // Seed via the debug harness (same OPFS-backed database the real app
  // reads once navigated) rather than 20 real captures through the UI —
  // this test is about triage speed, not capture speed.
  await ready(page)
  for (let i = 0; i < 20; i++) {
    await page.evaluate(
      (input) => window.__lifeHelperDb.mutate(input),
      seedInboxTask(`triage-item-${i.toString()}`, `Item ${i.toString()}`, 1000 + i),
    )
  }

  await page.goto('/inbox')
  await page.getByRole('button', { name: 'Start triage' }).click()
  await expect(page.getByText(itemsLeftText(20))).toBeVisible()

  // Rotates through every single-keystroke action (deliberately excluding
  // D/date and P/project, which need a Sheet interaction beyond one key).
  const keys = ['t', 'Enter', 's', 'n', 'r', 'Backspace']
  const start = Date.now()
  for (let i = 0; i < 20; i++) {
    await page.keyboard.press(keys[i % keys.length])
    const remaining = 19 - i
    if (remaining > 0) {
      await expect(page.getByText(itemsLeftText(remaining))).toBeVisible()
    } else {
      await expect(page.getByText('Inbox zero. Nice work.')).toBeVisible()
    }
  }
  const elapsedMs = Date.now() - start

  expect(elapsedMs).toBeLessThan(90_000)
})

test('every triage action is undoable for 10 seconds via a toast', async ({ page }) => {
  await ready(page)
  await page.evaluate(
    (input) => window.__lifeHelperDb.mutate(input),
    seedInboxTask('undo-item', 'Undo me', 1000),
  )

  await page.goto('/inbox')
  await page.getByRole('button', { name: 'Start triage' }).click()
  await expect(page.getByRole('heading', { name: 'Undo me' })).toBeVisible()

  await page.keyboard.press('Backspace')
  await expect(page.getByText('Deleted')).toBeVisible()
  await expect(page.getByText('Inbox zero. Nice work.')).toBeVisible()

  await page.getByRole('button', { name: 'Undo' }).click()

  // Undo's write reactively restores the item to the live inbox query, so
  // it reappears as the current triage item directly — no re-entry needed.
  await expect(page.getByRole('heading', { name: 'Undo me' })).toBeVisible()
})

test('leaving triage mid-way loses nothing: exiting and coming back keeps the remaining items', async ({
  page,
}) => {
  await ready(page)
  await page.evaluate(
    (input) => window.__lifeHelperDb.mutate(input),
    seedInboxTask('stay-1', 'Stays in inbox 1', 1000),
  )
  await page.evaluate(
    (input) => window.__lifeHelperDb.mutate(input),
    seedInboxTask('stay-2', 'Stays in inbox 2', 1001),
  )

  await page.goto('/inbox')
  await page.getByRole('button', { name: 'Start triage' }).click()
  await page.keyboard.press('Enter') // triage exactly one of the two

  await page.getByRole('button', { name: 'Exit triage' }).click()

  // Back on the inbox list (not triage): exactly one item remains, and
  // it's durably the un-triaged one, not just something still on screen.
  await expect(page.getByRole('button', { name: 'Start triage' })).toBeVisible()

  // /inbox is a different HTML entry point than debug-db.html, so the
  // harness global doesn't survive the earlier goto('/inbox') — re-attach
  // to the same OPFS-backed database by navigating back to it.
  await ready(page)
  const remainingTitles = await page.evaluate(() =>
    window.__lifeHelperDb.query(
      "SELECT title FROM items WHERE kind='task' AND status='inbox' AND deleted_at IS NULL",
    ),
  )
  expect(remainingTitles).toEqual([{ title: 'Stays in inbox 1' }])
})
