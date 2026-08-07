import '@testing-library/jest-dom/vitest'
import { afterEach } from 'vitest'
import { cleanup } from '@testing-library/react'

// vitest.config's `globals: false` means testing-library's own afterEach-based
// auto cleanup (which looks for a global `afterEach`) never registers, so
// every render from a previous test in the same file stays mounted.
afterEach(() => {
  cleanup()
})

// jsdom 30 has no Web Locks API at all — unlike HTMLDialogElement.showModal
// (see Sheet.tsx), there isn't even a `navigator.locks` property to probe,
// so `src/db/client.ts`'s module-level `export const dbClient = new
// DbClient()` throws inside its async init() the moment any component
// (starting with Part B1's CaptureRoute) imports it, even in test files
// that never render that component — the import alone runs the singleton's
// constructor. A minimal same-tab-only polyfill is enough for unit tests:
// nothing here needs cross-tab lock queueing, only that `request()` doesn't
// throw and grants the lock once, which is exactly what a single jsdom
// "tab" ever needs.
if (typeof navigator !== 'undefined' && !('locks' in navigator)) {
  const held = new Set<string>()
  type LockCallback = (lock: { name: string } | null) => unknown
  Object.defineProperty(navigator, 'locks', {
    configurable: true,
    value: {
      request(
        name: string,
        optionsOrCallback: { ifAvailable?: boolean } | LockCallback,
        maybeCallback?: LockCallback,
      ) {
        const hasOptions = typeof optionsOrCallback !== 'function'
        const options = hasOptions ? optionsOrCallback : {}
        const callback = (hasOptions ? maybeCallback : optionsOrCallback) as LockCallback

        if (held.has(name)) {
          // Real Web Locks would queue; nothing in this test environment
          // ever releases a held lock (the app holds it for the tab's
          // lifetime), so an unresolved promise is an honest match.
          if (options.ifAvailable) return Promise.resolve(callback(null))
          return new Promise(() => {})
        }
        held.add(name)
        return Promise.resolve(callback({ name }))
      },
    },
  })
}

// jsdom also has no Worker constructor. Once the lock above resolves,
// DbClient.setUpAsLeader() reaches `new Worker(...)`, which would otherwise
// throw a synchronous ReferenceError inside an async method — an unhandled
// rejection that fails the whole run even though no test asserts anything
// about it. A Worker that never actually delivers a message is enough:
// Comlink's calls against it (e.g. `api.init()`) simply never resolve,
// which is a silent no-op for every unit test that doesn't await them —
// exactly the tests in this file, since anything that needs a real,
// responsive dbClient mocks `src/db/client.ts` outright (see
// CaptureRoute.test.tsx) rather than depending on this stub.
if (typeof Worker === 'undefined') {
  class NoopWorker extends EventTarget {
    postMessage(): void {
      // Deliberately inert — see comment above.
    }
    terminate(): void {
      // Deliberately inert — see comment above.
    }
  }
  Object.defineProperty(globalThis, 'Worker', { configurable: true, value: NoopWorker })
}
