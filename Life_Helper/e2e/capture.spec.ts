import { expect, test } from '@playwright/test'

test('the global shortcut opens capture and focuses the field, from any route', async ({
  page,
}) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Life Helper' })).toBeVisible()

  await page.keyboard.press('Control+k')

  await expect(page).toHaveURL(/\/capture$/)
  await expect(page.getByLabel('Capture')).toBeFocused()
})

test('capture works fully offline: type, press Enter, item appears and the field stays focused', async ({
  page,
  context,
}) => {
  await page.goto('/capture')
  await expect(page.getByLabel('Capture')).toBeFocused()
  // Wait for the recent-captures query to round-trip through the real
  // worker + sqlite-wasm + OPFS pipeline at least once before cutting
  // network — otherwise this fresh page load might still be mid-fetch for
  // the worker's wasm binary (the service worker doesn't control a page
  // until its *second* navigation, since generateSW's default is
  // clientsClaim: false), and going offline before that fetch lands is a
  // race in this test, not the offline capture behavior it's meant to
  // verify.
  await expect(
    page.getByText('Nothing captured yet. Type above and press Enter to add your first item.'),
  ).toBeVisible()

  await context.setOffline(true)

  const field = page.getByLabel('Capture')
  await field.fill('Buy milk offline')
  await field.press('Enter')

  await expect(page.getByText('Buy milk offline')).toBeVisible()
  await expect(field).toHaveValue('')
  await expect(field).toBeFocused()

  await context.setOffline(false)
})

test('Shift+Enter inserts a newline instead of submitting', async ({ page }) => {
  await page.goto('/capture')
  const field = page.getByLabel('Capture')

  await field.fill('line one')
  await field.press('Shift+Enter')
  await field.pressSequentially('line two')

  await expect(field).toHaveValue('line one\nline two')
  // Scoped to the recent-captures region rather than a page-wide getByText:
  // Playwright's text matching considers a <textarea>'s own value when
  // walking the DOM, so an unscoped getByText('line one') matches the
  // field itself (which legitimately still contains that text) as well as
  // any real captured item — this only proves nothing was *captured*.
  await expect(page.getByRole('region').getByText('line one')).toHaveCount(0)
  await expect(
    page.getByText('Nothing captured yet. Type above and press Enter to add your first item.'),
  ).toBeVisible()
})

test('consecutive captures never lose focus and each appears in the recent list', async ({
  page,
}) => {
  await page.goto('/capture')
  const field = page.getByLabel('Capture')

  await field.fill('First capture')
  await field.press('Enter')
  await expect(page.getByText('First capture')).toBeVisible()
  await expect(field).toBeFocused()

  await field.fill('Second capture')
  await field.press('Enter')
  await expect(page.getByText('Second capture')).toBeVisible()
  await expect(field).toBeFocused()
})

test('a captured item survives a reload', async ({ page }) => {
  await page.goto('/capture')
  const field = page.getByLabel('Capture')
  await field.fill('Survives reload')
  await field.press('Enter')
  await expect(page.getByText('Survives reload')).toBeVisible()

  await page.reload()

  await expect(page.getByText('Survives reload')).toBeVisible()
})
