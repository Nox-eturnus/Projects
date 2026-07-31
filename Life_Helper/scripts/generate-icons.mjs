// Generates the PWA icon set from the designed source image
// (assets/app-icon-source.jpeg) using jimp — a pure-JS image library with
// no native bindings. We previously tried `sharp` via
// @vite-pwa/assets-generator, but its prebuilt native binding fails to
// `dlopen` on this Windows + Node 26.4.0 combination; jimp has no such
// binary to fail.
import { Jimp } from 'jimp'
import { writeFileSync, mkdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const sourcePath = path.join(__dirname, '..', 'assets', 'app-icon-source.jpeg')
const outDir = path.join(__dirname, '..', 'public')
mkdirSync(outDir, { recursive: true })

const targets = [
  { name: 'pwa-192x192.png', size: 192 },
  { name: 'pwa-512x512.png', size: 512 },
  { name: 'maskable-icon-512x512.png', size: 512 },
  { name: 'apple-touch-icon-180x180.png', size: 180 },
  { name: 'favicon-32x32.png', size: 32 },
]

const source = await Jimp.read(sourcePath)

for (const t of targets) {
  const resized = source.clone().cover({ w: t.size, h: t.size })
  const buffer = await resized.getBuffer('image/png')
  writeFileSync(path.join(outDir, t.name), buffer)
  console.log(`wrote ${t.name} (${buffer.length} bytes)`)
}
