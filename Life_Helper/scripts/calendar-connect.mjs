#!/usr/bin/env node
/**
 * `pnpm calendar:connect` — connects (or reconnects) Google Calendar.
 *
 * Runs Google's OAuth consent once, on this machine, and stores the
 * resulting refresh token directly as the edge Worker's
 * GOOGLE_REFRESH_TOKEN secret. The plan (Part C3, D1) has the Worker hold
 * the refresh token as a Wrangler secret — and Wrangler secrets can only
 * be written from the CLI, not by the Worker itself. So consent happens
 * here, not in the app. The token is piped to `wrangler secret put` and
 * never printed, logged, or written to disk; the app never sees it.
 *
 * Uses a loopback redirect (http://127.0.0.1:<random port>) with PKCE and a
 * state check, which is what a Google "Desktop app" OAuth client allows
 * without registering any redirect URI. Scope is calendar.readonly only.
 *
 * Needs: GOOGLE_CLIENT_ID in edge/wrangler.toml's [vars], the client
 * secret (GOOGLE_CLIENT_SECRET env var, or typed at the hidden prompt), a
 * deployed Worker, and `npx wrangler login`. See docs/phase_C3_calendar.md.
 */
import { createHash, randomBytes } from 'node:crypto'
import { spawn } from 'node:child_process'
import { createServer } from 'node:http'
import { putSecret, wranglerVar } from './wranglerSecret.mjs'

const SCOPE = 'https://www.googleapis.com/auth/calendar.readonly'
const TIMEOUT_MS = 5 * 60 * 1000

function fail(message) {
  console.error(`\n${message}`)
  process.exit(1)
}

function base64url(bytes) {
  return Buffer.from(bytes).toString('base64url')
}

/** Reads a line without echoing it — for the client secret. */
function promptHidden(question) {
  if (!process.stdin.isTTY) {
    fail('No terminal to prompt in. Set GOOGLE_CLIENT_SECRET in the environment instead.')
  }
  process.stdout.write(question)
  process.stdin.setRawMode(true)
  process.stdin.resume()
  process.stdin.setEncoding('utf8')
  let value = ''
  return new Promise((resolve) => {
    function onData(chunk) {
      for (const char of chunk) {
        if (char === '\r' || char === '\n') {
          done()
          resolve(value)
          return
        }
        if (char === '\u0003') {
          done()
          fail('Cancelled.')
        }
        if (char === '\u007f' || char === '\b') value = value.slice(0, -1)
        else value += char
      }
    }
    function done() {
      process.stdin.setRawMode(false)
      process.stdin.pause()
      process.stdin.off('data', onData)
      process.stdout.write('\n')
    }
    process.stdin.on('data', onData)
  })
}

function openBrowser(url) {
  // rundll32 rather than `start`: cmd.exe would split the URL at every "&".
  const [command, args] =
    process.platform === 'win32'
      ? ['rundll32', ['url.dll,FileProtocolHandler', url]]
      : process.platform === 'darwin'
        ? ['open', [url]]
        : ['xdg-open', [url]]
  const child = spawn(command, args, { stdio: 'ignore', detached: true })
  child.on('error', () => {
    // The URL is printed too; opening it automatically is only a convenience.
  })
  child.unref()
}

/** Serves one request on the loopback address and resolves with its query. */
function waitForRedirect(server) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      reject(new Error('Timed out waiting for Google (5 minutes). Run it again.'))
    }, TIMEOUT_MS)
    server.on('request', (request, response) => {
      const url = new URL(request.url ?? '/', 'http://127.0.0.1')
      if (url.pathname !== '/callback') {
        response.writeHead(404).end()
        return
      }
      response.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' })
      response.end(
        '<p style="font-family:system-ui;padding:2rem">Done — you can close this tab and go back to the terminal.</p>',
      )
      clearTimeout(timer)
      resolve(url.searchParams)
    })
  })
}

const clientId = process.env.GOOGLE_CLIENT_ID ?? wranglerVar('GOOGLE_CLIENT_ID')
if (!clientId) {
  fail(
    'No OAuth client ID. Put it in edge/wrangler.toml under [vars] as GOOGLE_CLIENT_ID\n' +
      '(then `pnpm edge:deploy`), and run this again.',
  )
}
const clientSecret =
  process.env.GOOGLE_CLIENT_SECRET ?? (await promptHidden('OAuth client secret (hidden): '))
if (!clientSecret) fail('No client secret given.')

const verifier = base64url(randomBytes(32))
const challenge = base64url(createHash('sha256').update(verifier).digest())
const state = base64url(randomBytes(16))

const server = createServer()
await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve))
const port = server.address().port
const redirectUri = `http://127.0.0.1:${String(port)}/callback`

const consent = new URL('https://accounts.google.com/o/oauth2/v2/auth')
consent.search = new URLSearchParams({
  client_id: clientId,
  redirect_uri: redirectUri,
  response_type: 'code',
  scope: SCOPE,
  // offline + consent: the only combination that reliably returns a
  // refresh token, including on a reconnect after a revoke.
  access_type: 'offline',
  prompt: 'consent',
  code_challenge: challenge,
  code_challenge_method: 'S256',
  state,
}).toString()

console.log(
  `Opening Google's consent page. If it doesn't open, visit:\n\n  ${consent.toString()}\n`,
)
openBrowser(consent.toString())

let params
try {
  params = await waitForRedirect(server)
} catch (error) {
  fail(error.message)
} finally {
  server.close()
}

if (params.get('state') !== state) fail('The response did not match this request (state mismatch).')
if (params.get('error')) fail(`Google declined: ${params.get('error')}`)
const code = params.get('code')
if (!code) fail('Google returned no authorization code.')

const tokenResponse = await fetch('https://oauth2.googleapis.com/token', {
  method: 'POST',
  headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  body: new URLSearchParams({
    grant_type: 'authorization_code',
    code,
    client_id: clientId,
    client_secret: clientSecret,
    redirect_uri: redirectUri,
    code_verifier: verifier,
  }),
})
const tokens = await tokenResponse.json()
if (!tokenResponse.ok) {
  fail(`Token exchange failed: ${tokens.error ?? tokenResponse.status}. Check the client secret.`)
}
if (!tokens.refresh_token) fail('Google returned no refresh token. Run this again.')
if (
  !String(tokens.scope ?? '')
    .split(' ')
    .includes(SCOPE)
) {
  fail('Calendar access was not granted — tick the calendar permission on the consent screen.')
}

// Before storing anything: does the Calendar API answer? A 403 here means
// it isn't enabled on the Google Cloud project, which reconnecting can't fix.
const check = await fetch('https://www.googleapis.com/calendar/v3/calendars/primary?fields=id', {
  headers: { Authorization: `Bearer ${tokens.access_token}` },
})
if (!check.ok) {
  fail(
    `The Calendar API answered ${String(check.status)}. Enable "Google Calendar API" for this\n` +
      'project in the Google Cloud console, then run this again.',
  )
}

try {
  await putSecret('GOOGLE_CLIENT_SECRET', clientSecret)
  await putSecret('GOOGLE_REFRESH_TOKEN', tokens.refresh_token)
} catch (error) {
  fail(
    `Couldn't store the secrets: ${error.message}\n` +
      'Is the Worker deployed (pnpm edge:deploy) and are you logged in (npx wrangler login)?',
  )
}

console.log('\nCalendar connected. The app picks it up on its next refresh.')
