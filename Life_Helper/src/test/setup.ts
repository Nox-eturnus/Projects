import '@testing-library/jest-dom/vitest'
import { afterEach } from 'vitest'
import { cleanup } from '@testing-library/react'

// vitest.config's `globals: false` means testing-library's own afterEach-based
// auto cleanup (which looks for a global `afterEach`) never registers, so
// every render from a previous test in the same file stays mounted.
afterEach(() => {
  cleanup()
})
