/// <reference types="vite/client" />
/// <reference types="vite-plugin-pwa/client" />
/// <reference types="vite-plugin-pwa/react" />

interface ImportMetaEnv {
  /** Optional build-time default for Settings → Calendar's Worker URL (Part C3). */
  readonly VITE_EDGE_URL?: string
}
