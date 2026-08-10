import { expect, test, type Page } from '@playwright/test'

// PwaPrompts.module.css's "ready to work offline" toast is bottom-center,
// position: fixed, z-index: 1000 — the exact same collision Part B3 found
// with TriageView's undo toast, just a different victim this time (the
// integrity-check button, not a time-limited undo). A real single user
// dismisses this once and never sees it again; a fresh Playwright context
// sees it on every test. There's no time pressure on this button the way
// there was on undo, so dismissing it first (as a real user eventually
// would) is the honest fix here, not another z-index bump.
async function dismissPwaPromptIfPresent(page: Page): Promise<void> {
  const dismiss = page.getByRole('button', { name: 'Dismiss' })
  if (await dismiss.isVisible().catch(() => false)) {
    await dismiss.click()
  }
}

test('ops replay verification passes against a real, non-trivial device history', async ({
  page,
}) => {
  // Builds real history through the actual UI — capture, then triage —
  // rather than seeding rows directly, so this exercises the exact write
  // paths a real 7-day usage period would produce (Part B4's capture gate
  // requires the replay check to pass against real captured data, not
  // fixtures; this is the closest an automated test can get to that
  // without an actual device history).
  // Navigates within the app (nav links / keyboard shortcuts), never
  // page.goto() mid-flow: capture fires its write with `void`, not
  // awaited, and a hard navigation tears down the JS realm before an
  // in-flight write reaches the worker — losing it. A real user clicking
  // around doesn't have that problem, so neither should this test.
  await page.goto('/capture')
  const field = page.getByRole('textbox', { name: 'Capture' })
  await field.fill('Buy milk tomorrow ~15m')
  await field.press('Enter')
  await expect(page.getByText('Buy milk', { exact: true })).toBeVisible()
  await field.fill('Second item @Rahul')
  await field.press('Enter')
  await expect(page.getByText('Second item @Rahul')).toBeVisible()

  await page.getByRole('link', { name: 'Inbox' }).click()
  await page.getByRole('button', { name: 'Start triage' }).click()
  await expect(page.getByRole('button', { name: 'Exit triage' })).toBeVisible()
  await page.keyboard.press('t') // schedule the first (newest) item for today
  await expect(page.getByText('1 item left')).toBeVisible()
  await page.keyboard.press('Backspace') // delete the second
  await expect(page.getByText('Inbox zero. Nice work.')).toBeVisible()

  await page.getByRole('link', { name: 'Gallery' }).click()
  await dismissPwaPromptIfPresent(page)
  await page.getByRole('button', { name: 'Run ops replay verification' }).click()

  await expect(
    page.getByText('All tables match. Record this result in docs/usage_log.md.'),
  ).toBeVisible()
  await expect(page.getByText('FAIL')).toHaveCount(0)

  const rows = page.locator('table', { hasText: 'Live rows' }).locator('tbody tr')
  await expect(rows).not.toHaveCount(0)
})

test('ops replay verification passes on a fresh, empty device too', async ({ page }) => {
  await page.goto('/gallery')
  await dismissPwaPromptIfPresent(page)

  await page.getByRole('button', { name: 'Run ops replay verification' }).click()

  await expect(
    page.getByText('All tables match. Record this result in docs/usage_log.md.'),
  ).toBeVisible()
})
