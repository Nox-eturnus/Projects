#!/usr/bin/env node
/**
 * `pnpm edge:device-key` — generates the device key the edge Worker
 * accepts (its DEVICE_TOKEN secret) and stores it on the Worker.
 *
 * Unlike the Google secrets, this one is printed: you need to enter it in
 * Settings → Calendar on each of your devices. Running this again rotates
 * it — every device then needs the new one. Part D3's device pairing
 * replaces this shared key with per-device tokens.
 */
import { randomBytes } from 'node:crypto'
import { putSecret } from './wranglerSecret.mjs'

const key = randomBytes(32).toString('base64url')

try {
  await putSecret('DEVICE_TOKEN', key)
} catch (error) {
  console.error(`\nCouldn't store the device key: ${error.message}`)
  console.error(
    'Is the Worker deployed (pnpm edge:deploy) and are you logged in (npx wrangler login)?',
  )
  process.exit(1)
}

console.log(`
Device key stored on the Worker. Enter it in Settings → Calendar on each device:

    ${key}

It isn't saved anywhere else. Run this again to replace it.`)
