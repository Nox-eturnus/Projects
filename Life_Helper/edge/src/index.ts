/**
 * The edge Worker (surface EDGE). For Part C3 it does exactly one thing:
 * `GET /calendar/events`, a read-only, normalized proxy onto the user's
 * Google Calendar. Part D1 adds `/sync`, `/pair`, and `/push/register`
 * to this same Worker.
 *
 * Dumb by design (Decision 11): no state, no storage, no logging of
 * anything it relays. Its secrets — the Google client secret and refresh
 * token, and this device key — are Wrangler secrets: never in the
 * repository, never sent to a client (Decision 8). All it ever returns is
 * the normalized event list for the range asked for.
 *
 * Authentication until Part D3's device pairing exists: one shared device
 * key (the `DEVICE_TOKEN` secret), entered once per device in the app's
 * Settings, sent as a bearer token. It fails closed: no key configured,
 * or one too short to be a real random secret, and every request is
 * refused.
 */
import type { EdgeErrorBody, EdgeErrorCode, EventsResponse } from './contract.js'
import { EdgeError, getAccessToken, listEvents } from './google.js'

export interface Env {
  /** Plain vars, in wrangler.toml. */
  readonly GOOGLE_CLIENT_ID?: string
  /** Comma-separated origins allowed to call this Worker (the Pages app, local dev). */
  readonly ALLOWED_ORIGINS?: string
  /** Wrangler secrets. */
  readonly GOOGLE_CLIENT_SECRET?: string
  readonly GOOGLE_REFRESH_TOKEN?: string
  readonly DEVICE_TOKEN?: string
}

const DAY_MS = 24 * 60 * 60 * 1000
/** The app asks for two days; a fortnight is headroom, not an invitation. */
export const MAX_RANGE_MS = 14 * DAY_MS
/** `pnpm edge:device-key` generates 43 characters; anything this short wasn't generated. */
const MIN_DEVICE_TOKEN_LENGTH = 32

function allowedOrigins(env: Env): string[] {
  return (env.ALLOWED_ORIGINS ?? '')
    .split(',')
    .map((origin) => origin.trim())
    .filter((origin) => origin.length > 0)
}

function corsHeaders(request: Request, env: Env): Record<string, string> {
  const origin = request.headers.get('Origin')
  if (origin === null || !allowedOrigins(env).includes(origin)) return {}
  return {
    'Access-Control-Allow-Origin': origin,
    'Access-Control-Allow-Methods': 'GET, OPTIONS',
    'Access-Control-Allow-Headers': 'Authorization',
    // Chromium caps this at two hours; it saves a preflight per poll.
    'Access-Control-Max-Age': '7200',
    Vary: 'Origin',
  }
}

function json(body: unknown, status: number, headers: Record<string, string>): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', 'Cache-Control': 'no-store', ...headers },
  })
}

function error(code: EdgeErrorCode, status: number, headers: Record<string, string>): Response {
  const body: EdgeErrorBody = { error: code }
  return json(body, status, headers)
}

async function digest(value: string): Promise<Uint8Array> {
  return new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(value)))
}

/**
 * Compares SHA-256 digests rather than the strings: equal-length inputs,
 * compared in full every time, so how long a rejection takes says nothing
 * about how much of a guessed key was right.
 */
async function sameSecret(a: string, b: string): Promise<boolean> {
  const [x, y] = await Promise.all([digest(a), digest(b)])
  let difference = 0
  for (let i = 0; i < x.length; i++) difference |= x[i] ^ y[i]
  return difference === 0
}

async function isAuthorized(request: Request, env: Env): Promise<boolean> {
  const expected = env.DEVICE_TOKEN
  if (expected === undefined || expected.length < MIN_DEVICE_TOKEN_LENGTH) return false
  const header = request.headers.get('Authorization') ?? ''
  const match = /^Bearer (.+)$/.exec(header)
  if (!match) return false
  return sameSecret(match[1], expected)
}

function parseRange(url: URL): { from: number; to: number } | null {
  const from = Number(url.searchParams.get('from'))
  const to = Number(url.searchParams.get('to'))
  if (!Number.isInteger(from) || !Number.isInteger(to)) return null
  if (to <= from || to - from > MAX_RANGE_MS) return null
  return { from, to }
}

export async function handle(
  request: Request,
  env: Env,
  fetcher: typeof fetch = fetch,
): Promise<Response> {
  const cors = corsHeaders(request, env)
  const url = new URL(request.url)

  if (request.method === 'OPTIONS') {
    return new Response(null, { status: Object.keys(cors).length > 0 ? 204 : 403, headers: cors })
  }

  if (url.pathname !== '/calendar/events') return error('not_found', 404, cors)
  if (request.method !== 'GET') return error('bad_request', 405, cors)
  if (!(await isAuthorized(request, env))) return error('unauthorized', 401, cors)

  const range = parseRange(url)
  if (!range) return error('bad_request', 400, cors)

  const { GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN } = env
  if (!GOOGLE_CLIENT_ID || !GOOGLE_CLIENT_SECRET || !GOOGLE_REFRESH_TOKEN) {
    return error('not_configured', 503, cors)
  }

  try {
    const accessToken = await getAccessToken(
      {
        clientId: GOOGLE_CLIENT_ID,
        clientSecret: GOOGLE_CLIENT_SECRET,
        refreshToken: GOOGLE_REFRESH_TOKEN,
      },
      fetcher,
    )
    const events = await listEvents(accessToken, range.from, range.to, fetcher)
    const body: EventsResponse = { events, fetchedAt: Date.now() }
    return json(body, 200, cors)
  } catch (caught) {
    if (caught instanceof EdgeError) return error(caught.code, caught.status, cors)
    return error('upstream_error', 502, cors)
  }
}

export default {
  fetch(request: Request, env: Env): Promise<Response> {
    return handle(request, env)
  },
}
