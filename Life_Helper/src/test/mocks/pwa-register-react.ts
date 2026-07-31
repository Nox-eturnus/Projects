// Stand-in for vite-plugin-pwa's `virtual:pwa-register/react` virtual
// module, which only resolves inside a real Vite dev/build pipeline, not
// under Vitest. Aliased in for test runs only — see vite.config.ts.
import { useState } from 'react'

export function useRegisterSW() {
  const [offlineReady, setOfflineReady] = useState(false)
  const [needRefresh, setNeedRefresh] = useState(false)

  return {
    offlineReady: [offlineReady, setOfflineReady] as const,
    needRefresh: [needRefresh, setNeedRefresh] as const,
    updateServiceWorker: async () => {},
  }
}
