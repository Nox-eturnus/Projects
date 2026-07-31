import { expect, test } from '@playwright/test'

test('loads the shell and shows the app heading', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Life Helper' })).toBeVisible()
})

test('registers a service worker and exposes a valid manifest', async ({ page }) => {
  await page.goto('/')
  const origin = new URL(page.url()).origin

  const registration = await page.evaluate(async () => {
    const reg = await navigator.serviceWorker.ready
    return { scope: reg.scope, hasActiveWorker: reg.active !== null }
  })
  expect(registration.hasActiveWorker).toBe(true)
  expect(registration.scope).toBe(`${origin}/`)

  const manifestHref = await page.locator('link[rel="manifest"]').getAttribute('href')
  if (!manifestHref) {
    throw new Error('Expected a <link rel="manifest"> with an href')
  }

  interface WebAppManifest {
    name: string
    icons: { sizes: string; purpose: string }[]
  }

  const manifestResponse = await page.request.get(new URL(manifestHref, origin).toString())
  expect(manifestResponse.ok()).toBe(true)
  const manifest = (await manifestResponse.json()) as WebAppManifest
  expect(manifest.name).toBe('Life Helper')
  expect(manifest.icons).toEqual(
    expect.arrayContaining([
      expect.objectContaining({ sizes: '192x192', purpose: 'any' }),
      expect.objectContaining({ sizes: '512x512', purpose: 'any' }),
      expect.objectContaining({ sizes: '512x512', purpose: 'maskable' }),
    ]),
  )
})
