/**
 * Test-only harness exposing dbClient on `window` for Playwright/manual
 * browser driving (see debug-db.html and e2e/db.spec.ts). Not imported by
 * the real app entry point.
 */
import { dbClient } from './client.js'
import type { MutateInput } from './ops.js'

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

const out = document.getElementById('out')

function render(text: string): void {
  if (out) out.textContent = text
}

const readyMarker = dbClient.getDeviceId().then((id) => {
  render(`ready device=${id}`)
})

window.__lifeHelperDb = {
  mutate: (input) => dbClient.mutate(input),
  query: (sql, params = []) => dbClient.query(sql, params),
  getDeviceId: () => dbClient.getDeviceId(),
  ready: readyMarker,
}

dbClient.subscribe((tables) => {
  render(`changed: ${tables.join(',')}`)
})
