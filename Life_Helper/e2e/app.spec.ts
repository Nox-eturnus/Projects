import { expect, test } from '@playwright/test'

test('loads the shell and shows the app heading', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Life Helper' })).toBeVisible()
})
