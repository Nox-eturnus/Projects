import { expect, test } from '@playwright/test'

test('a load that opens on Today records a cold start, which the gate report shows', async ({
  page,
}) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Today', level: 1 })).toBeVisible()
  // Recorded on the frame after Today renders with its data.
  await expect
    .poll(() => page.evaluate(() => window.localStorage.getItem('life-helper-gate-cold-starts')))
    .not.toBeNull()

  // An in-app navigation, so this load's measurement isn't replaced.
  await page.getByRole('link', { name: 'Settings' }).click()
  await page.getByRole('link', { name: 'Today gate report' }).click()

  await expect(page.getByRole('heading', { name: 'Today gate', level: 1 })).toBeVisible()
  // Desktop Chromium isn't Android: recorded, but not counted toward the gate.
  await expect(page.getByText(/\d+ms \(not Android\)/)).toHaveCount(1)
  await expect(page.getByText('0 of 3 Android cold starts recorded so far').first()).toBeVisible()
  // Today was opened today.
  const todayRow = page.getByRole('row').nth(1)
  await expect(todayRow.getByRole('cell').first()).toHaveText('yes')
})

test('a load that starts somewhere else is not a cold start to Today', async ({ page }) => {
  await page.goto('/settings')
  await page.getByRole('link', { name: 'Today', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Today', level: 1 })).toBeVisible()
  await page.waitForTimeout(300)
  expect(
    await page.evaluate(() => window.localStorage.getItem('life-helper-gate-cold-starts')),
  ).toBeNull()
})
