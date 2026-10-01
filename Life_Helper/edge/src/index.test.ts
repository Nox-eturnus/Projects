// @vitest-environment node
import { describe, expect, it, vi } from 'vitest'
import type { EdgeErrorBody, EventsResponse } from './contract.js'
import { CALENDAR_SCOPE, normalizeEvent } from './google.js'
import { handle, MAX_RANGE_MS, type Env } from './index.js'

const DEVICE_TOKEN = 'k'.repeat(43)
const APP_ORIGIN = 'https://life-helper.pages.dev'
const ENV: Env = {
  GOOGLE_CLIENT_ID: 'client-id.apps.googleusercontent.com',
  GOOGLE_CLIENT_SECRET: 'client-secret',
  GOOGLE_REFRESH_TOKEN: 'refresh-token',
  DEVICE_TOKEN,
  ALLOWED_ORIGINS: `${APP_ORIGIN}, http://localhost:5173`,
}

const FROM = Date.UTC(2026, 8, 11)
const TO = FROM + 2 * 24 * 60 * 60 * 1000

function request(
  path = `/calendar/events?from=${String(FROM)}&to=${String(TO)}`,
  init: { method?: string; token?: string | null; origin?: string } = {},
): Request {
  const headers = new Headers()
  const token = init.token === undefined ? DEVICE_TOKEN : init.token
  if (token !== null) headers.set('Authorization', `Bearer ${token}`)
  headers.set('Origin', init.origin ?? APP_ORIGIN)
  return new Request(`https://life-helper-edge.example.workers.dev${path}`, {
    method: init.method ?? 'GET',
    headers,
  })
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

/** A fake Google: the token endpoint, then one events page per call. */
function google(options: {
  token?: Response
  pages?: Response[]
}): ReturnType<typeof vi.fn<typeof fetch>> {
  const pages = [...(options.pages ?? [jsonResponse({ items: [] })])]
  return vi.fn<typeof fetch>((input) => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
    if (url.startsWith('https://oauth2.googleapis.com/token')) {
      return Promise.resolve(
        options.token ??
          jsonResponse({ access_token: 'ya29.fake-access-token', scope: CALENDAR_SCOPE }),
      )
    }
    const next = pages.shift()
    return next ? Promise.resolve(next) : Promise.reject(new Error('unexpected call'))
  })
}

async function errorOf(response: Response): Promise<string> {
  return ((await response.json()) as EdgeErrorBody).error
}

describe('CORS', () => {
  it('answers a preflight from the app with the headers the app needs', async () => {
    const response = await handle(request('/calendar/events', { method: 'OPTIONS' }), ENV)
    expect(response.status).toBe(204)
    expect(response.headers.get('Access-Control-Allow-Origin')).toBe(APP_ORIGIN)
    expect(response.headers.get('Access-Control-Allow-Headers')).toBe('Authorization')
  })

  it('refuses a preflight from any other origin, with no CORS headers', async () => {
    const response = await handle(
      request('/calendar/events', { method: 'OPTIONS', origin: 'https://evil.example' }),
      ENV,
    )
    expect(response.status).toBe(403)
    expect(response.headers.get('Access-Control-Allow-Origin')).toBeNull()
  })
})

describe('authentication fails closed', () => {
  it('no key, the wrong key, or a malformed header: 401', async () => {
    const fetcher = google({})
    for (const token of [null, 'wrong'.repeat(10), '']) {
      const response = await handle(request(undefined, { token }), ENV, fetcher)
      expect(response.status).toBe(401)
      expect(await errorOf(response)).toBe('unauthorized')
    }
    expect(fetcher).not.toHaveBeenCalled()
  })

  it('refuses everything while no device key is configured, or one too short to be real', async () => {
    for (const DEVICE_TOKEN of [undefined, 'short']) {
      const response = await handle(request(undefined, { token: 'short' }), {
        ...ENV,
        DEVICE_TOKEN,
      })
      expect(response.status).toBe(401)
    }
  })

  it('is checked before anything reaches Google', async () => {
    const fetcher = google({})
    await handle(request(undefined, { token: 'x'.repeat(43) }), ENV, fetcher)
    expect(fetcher).not.toHaveBeenCalled()
  })
})

describe('GET /calendar/events', () => {
  it('returns normalized events, with CORS headers and no caching', async () => {
    const fetcher = google({
      pages: [
        jsonResponse({
          items: [
            {
              id: 'a',
              summary: 'Standup',
              start: { dateTime: '2026-09-11T09:00:00+05:30' },
              end: { dateTime: '2026-09-11T09:15:00+05:30' },
            },
            {
              id: 'b',
              summary: 'Birthday',
              start: { date: '2026-09-12' },
              end: { date: '2026-09-13' },
            },
          ],
        }),
      ],
    })
    const response = await handle(request(), ENV, fetcher)
    expect(response.status).toBe(200)
    expect(response.headers.get('Cache-Control')).toBe('no-store')
    expect(response.headers.get('Access-Control-Allow-Origin')).toBe(APP_ORIGIN)
    const body = (await response.json()) as EventsResponse
    expect(body.events).toEqual([
      {
        id: 'a',
        title: 'Standup',
        allDay: false,
        start: Date.parse('2026-09-11T09:00:00+05:30'),
        end: Date.parse('2026-09-11T09:15:00+05:30'),
        busy: true,
      },
      {
        id: 'b',
        title: 'Birthday',
        allDay: true,
        startDate: '2026-09-12',
        endDate: '2026-09-13',
        busy: true,
      },
    ])
    expect(typeof body.fetchedAt).toBe('number')
  })

  it('asks Google for exactly the range, expanded recurrences, and only the fields it reads', async () => {
    const fetcher = google({})
    await handle(request(), ENV, fetcher)
    const eventsCall = fetcher.mock.calls[1]
    const url = new URL(eventsCall[0] as string)
    expect(url.searchParams.get('timeMin')).toBe(new Date(FROM).toISOString())
    expect(url.searchParams.get('timeMax')).toBe(new Date(TO).toISOString())
    expect(url.searchParams.get('singleEvents')).toBe('true')
    expect(url.searchParams.get('fields')).not.toMatch(/attendees|description|location/)
    expect((eventsCall[1]?.headers as Record<string, string>).Authorization).toBe(
      'Bearer ya29.fake-access-token',
    )
  })

  it('follows page tokens', async () => {
    const event = (id: string) => ({
      id,
      summary: id,
      start: { dateTime: '2026-09-11T10:00:00Z' },
      end: { dateTime: '2026-09-11T11:00:00Z' },
    })
    const fetcher = google({
      pages: [
        jsonResponse({ items: [event('p1')], nextPageToken: 'next' }),
        jsonResponse({ items: [event('p2')] }),
      ],
    })
    const body = (await (await handle(request(), ENV, fetcher)).json()) as EventsResponse
    expect(body.events.map((e) => e.id)).toEqual(['p1', 'p2'])
    expect(new URL(fetcher.mock.calls[2][0] as string).searchParams.get('pageToken')).toBe('next')
  })

  it('rejects a missing, inverted, or oversized range', async () => {
    for (const path of [
      '/calendar/events',
      `/calendar/events?from=${String(TO)}&to=${String(FROM)}`,
      `/calendar/events?from=${String(FROM)}&to=${String(FROM + MAX_RANGE_MS + 1)}`,
      '/calendar/events?from=abc&to=def',
    ]) {
      expect((await handle(request(path), ENV, google({}))).status).toBe(400)
    }
  })

  it('unknown paths are 404', async () => {
    expect((await handle(request('/'), ENV)).status).toBe(404)
  })
})

describe('telling failures apart', () => {
  it('a missing Google secret is not_configured, not a crash', async () => {
    const response = await handle(request(), { ...ENV, GOOGLE_REFRESH_TOKEN: undefined })
    expect(response.status).toBe(503)
    expect(await errorOf(response)).toBe('not_configured')
  })

  it('a revoked or expired grant (invalid_grant) asks for a reconnect', async () => {
    const fetcher = google({ token: jsonResponse({ error: 'invalid_grant' }, 400) })
    const response = await handle(request(), ENV, fetcher)
    expect(response.status).toBe(403)
    expect(await errorOf(response)).toBe('reconnect_required')
  })

  it('a grant with the calendar permission unticked asks for a reconnect', async () => {
    const fetcher = google({ token: jsonResponse({ access_token: 'a', scope: 'openid email' }) })
    expect(await errorOf(await handle(request(), ENV, fetcher))).toBe('reconnect_required')
  })

  it('Calendar API 401, or 403 for insufficient permissions, asks for a reconnect', async () => {
    for (const page of [
      new Response('', { status: 401 }),
      new Response('{"error":{"errors":[{"reason":"insufficientPermissions"}]}}', { status: 403 }),
    ]) {
      expect(await errorOf(await handle(request(), ENV, google({ pages: [page] })))).toBe(
        'reconnect_required',
      )
    }
  })

  it('the Calendar API not being enabled is an upstream error — reconnecting would not help', async () => {
    const page = new Response('{"error":{"errors":[{"reason":"accessNotConfigured"}]}}', {
      status: 403,
    })
    const response = await handle(request(), ENV, google({ pages: [page] }))
    expect(response.status).toBe(502)
    expect(await errorOf(response)).toBe('upstream_error')
  })

  it('Google being down, or unreachable, is an upstream error', async () => {
    expect(
      await errorOf(
        await handle(request(), ENV, google({ token: new Response('', { status: 500 }) })),
      ),
    ).toBe('upstream_error')
    const unreachable = vi.fn<typeof fetch>(() => Promise.reject(new TypeError('network')))
    expect(await errorOf(await handle(request(), ENV, unreachable))).toBe('upstream_error')
  })
})

describe('secrets never leave the Worker', () => {
  it('no response, in any branch, contains the refresh token, client secret, device key, or access token', async () => {
    const secrets = [
      ENV.GOOGLE_REFRESH_TOKEN,
      ENV.GOOGLE_CLIENT_SECRET,
      DEVICE_TOKEN,
      'ya29.fake-access-token',
    ] as string[]
    const responses = await Promise.all([
      handle(request(), ENV, google({})),
      handle(request(), ENV, google({ token: jsonResponse({ error: 'invalid_grant' }, 400) })),
      handle(request(), ENV, google({ token: new Response('', { status: 500 }) })),
      handle(request(undefined, { token: 'wrong'.repeat(9) }), ENV),
      handle(request(), { ...ENV, GOOGLE_REFRESH_TOKEN: undefined }),
      handle(request('/calendar/events', { method: 'OPTIONS' }), ENV),
      handle(request('/nope'), ENV),
    ])
    for (const response of responses) {
      const text = [...response.headers.values(), await response.text()].join('\n')
      for (const secret of secrets) expect(text).not.toContain(secret)
    }
  })
})

describe('normalizeEvent', () => {
  it('drops cancelled and unplaceable events', () => {
    expect(
      normalizeEvent({
        id: 'x',
        status: 'cancelled',
        start: { date: '2026-09-11' },
        end: { date: '2026-09-12' },
      }),
    ).toBeNull()
    expect(normalizeEvent({ id: 'x' })).toBeNull()
    expect(
      normalizeEvent({ id: 'x', start: { dateTime: 'nonsense' }, end: { dateTime: 'nonsense' } }),
    ).toBeNull()
  })

  it('a "free" event is not busy; an untitled one gets a neutral title', () => {
    const event = normalizeEvent({
      id: 'x',
      summary: '  ',
      transparency: 'transparent',
      start: { dateTime: '2026-09-11T10:00:00Z' },
      end: { dateTime: '2026-09-11T11:00:00Z' },
    })
    expect(event).toMatchObject({ title: 'Untitled event', busy: false })
  })
})
