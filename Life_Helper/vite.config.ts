/// <reference types="vitest/config" />
import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const isTest = mode === 'test'
  // debug-db.html/src/db/debugHarness.ts give raw read/write access to the
  // local database with no auth gate. Fine for e2e (see playwright.config.ts,
  // which sets this) and dev, but it must never ship in the real deploy.
  const includeDebugHarness = process.env.LIFE_HELPER_INCLUDE_DEBUG_HARNESS === '1'

  return {
    test: {
      environment: 'jsdom',
      globals: false,
      setupFiles: ['./src/test/setup.ts'],
      css: true,
      coverage: {
        provider: 'v8',
        reporter: ['text', 'html'],
        exclude: ['e2e/**', 'src/test/**', '**/*.config.*'],
      },
      exclude: ['e2e/**', 'node_modules/**'],
    },
    build: includeDebugHarness
      ? {
          rollupOptions: {
            input: {
              main: fileURLToPath(new URL('./index.html', import.meta.url)),
              debugDb: fileURLToPath(new URL('./debug-db.html', import.meta.url)),
            },
          },
        }
      : undefined,
    resolve: isTest
      ? {
          alias: {
            'virtual:pwa-register/react': fileURLToPath(
              new URL('./src/test/mocks/pwa-register-react.ts', import.meta.url),
            ),
          },
        }
      : undefined,
    plugins: [
      react(),
      // The real PWA plugin's virtual module isn't resolvable under
      // Vitest's environment; it's aliased to a stub above instead.
      ...(isTest
        ? []
        : [
            VitePWA({
              registerType: 'prompt',
              includeAssets: ['favicon-32x32.png', 'apple-touch-icon-180x180.png'],
              manifest: {
                id: '/',
                name: 'Life Helper',
                short_name: 'Life Helper',
                description:
                  'A single-user, local-first, offline-capable personal operating system.',
                start_url: '/',
                scope: '/',
                display: 'standalone',
                background_color: '#141221',
                theme_color: '#141221',
                icons: [
                  {
                    src: '/pwa-192x192.png',
                    sizes: '192x192',
                    type: 'image/png',
                    purpose: 'any',
                  },
                  {
                    src: '/pwa-512x512.png',
                    sizes: '512x512',
                    type: 'image/png',
                    purpose: 'any',
                  },
                  {
                    src: '/maskable-icon-512x512.png',
                    sizes: '512x512',
                    type: 'image/png',
                    purpose: 'maskable',
                  },
                ],
              },
              workbox: {
                globPatterns: ['**/*.{js,css,html,svg,png,ico,webmanifest}'],
                navigateFallbackDenylist: [/^\/api\//],
              },
              devOptions: {
                enabled: true,
                type: 'module',
              },
            }),
          ]),
    ],
  }
})
