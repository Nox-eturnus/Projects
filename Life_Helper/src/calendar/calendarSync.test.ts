// @vitest-environment node
import { describe, expect, it, vi } from 'vitest'
import type { EventsResponse } from '../../edge/src/contract.js'
import { startOfLocalDay } from '../scheduling/localDay'
import { EMPTY_CACHE, parseCache, type CalendarCache } from './calendarStore'
import {
  coversDay,
  fetchEvents,
  nextCache,
  REFRESH_INTERVAL_MS,
  refreshRange,
  shouldRefresh,
  type FetchResult,
} from './calendarSync'

const CONNECTION = { edgeUrl: 'https://edge.example.workers.dev', deviceKey: 'key-123' }
const NOW = new Date(2026, 8, 11, 14).getTime()
const TODAY = startOfLocalDay(NOW)
const RANGE = refreshRange(NOW)

const BODY: EventsResponse = {
  fetchedAt: NOW,
  events: [
    { id: 'e', title: 'Standup', allDay: false, start: NOW, end: NOW + 900_000, busy: true },
  ],
}

function answering(response: Response | Error) {
  return vi.fn<typeof fetch>(() =>
    response instanceof Error ? Promise.reject(response) : Promise.resolve(response),
  )
}

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

describe('fetchEvents', () => {
  it('asks the Worker for the range with this device’s key', async () => {
    const fetcher = answering(json(BODY))
    expect(await fetchEvents(CONNECTION, RANGE, fetcher)).toEqual({ ok: true, body: BODY })
    const [url, init] = fetcher.mock.calls[0]
    const parsed = new URL(url as string)
    expect(parsed.origin + parsed.pathname).toBe('https://edge.example.workers.dev/calendar/events')
    expect(parsed.searchParams.get('from')).toBe(String(RANGE.from))
    expect((init?.headers as Record<string, string>).Authorization).toBe('Bearer key-123')
  })

  it('tells apart what each failure asks of the user', async () => {
    const cases: [Response | Error, string][] = [
      [new TypeError('Failed to fetch'), 'offline'],
      [json({ error: 'unauthorized' }, 401), 'unauthorized'],
      [json({ error: 'reconnect_required' }, 403), 'reconnect_required'],
      [json({ error: 'not_configured' }, 503), 'not_configured'],
      [json({ error: 'upstream_error' }, 502), 'upstream_error'],
      [new Response('<html>not json</html>', { status: 401 }), 'unauthorized'],
      [new Response('gateway', { status: 504 }), 'upstream_error'],
      [json({ not: 'events' }), 'upstream_error'],
    ]
    for (const [response, problem] of cases) {
      expect(await fetchEvents(CONNECTION, RANGE, answering(response))).toEqual({
        ok: false,
        problem,
      })
    }
  })
})

describe('the refresh cadence: on focus, at most every 15 minutes', () => {
  const fresh: CalendarCache = nextCache(EMPTY_CACHE, { ok: true, body: BODY }, RANGE, NOW)

  it('never refreshed: go', () => {
    expect(shouldRefresh(EMPTY_CACHE, NOW, false)).toBe(true)
  })

  it('within 15 minutes of the last attempt: no, unless the user asked', () => {
    expect(shouldRefresh(fresh, NOW + REFRESH_INTERVAL_MS - 1, false)).toBe(false)
    expect(shouldRefresh(fresh, NOW + REFRESH_INTERVAL_MS - 1, true)).toBe(true)
    expect(shouldRefresh(fresh, NOW + REFRESH_INTERVAL_MS, false)).toBe(true)
  })

  it('a failed attempt counts too, so being offline does not mean retrying on every focus', () => {
    const failed = nextCache(fresh, { ok: false, problem: 'offline' }, RANGE, NOW + 1000)
    expect(shouldRefresh(failed, NOW + 2000, false)).toBe(false)
  })

  it('a cache that does not cover today (a new day) retries after a minute, not fifteen', () => {
    const tomorrowMorning = new Date(2026, 8, 13, 8).getTime() // past the cached two days
    const lastTried = { ...fresh, lastAttemptAt: tomorrowMorning - 61_000 }
    expect(coversDay(lastTried, startOfLocalDay(tomorrowMorning))).toBe(false)
    expect(shouldRefresh(lastTried, tomorrowMorning, false)).toBe(true)
    expect(
      shouldRefresh(
        { ...lastTried, lastAttemptAt: tomorrowMorning - 30_000 },
        tomorrowMorning,
        false,
      ),
    ).toBe(false)
  })
})

describe('nextCache', () => {
  it('a success replaces the events and clears any problem', () => {
    const cache = nextCache(
      { ...EMPTY_CACHE, problem: 'offline' },
      { ok: true, body: BODY },
      RANGE,
      NOW,
    )
    expect(cache).toMatchObject({
      events: BODY.events,
      fetchedAt: NOW,
      problem: null,
      lastAttemptAt: NOW,
    })
    expect(coversDay(cache, TODAY)).toBe(true)
  })

  it('a failure keeps the last known events — Today stays usable, just stale', () => {
    const fresh = nextCache(EMPTY_CACHE, { ok: true, body: BODY }, RANGE, NOW)
    const failure: FetchResult = { ok: false, problem: 'reconnect_required' }
    const after = nextCache(fresh, failure, RANGE, NOW + 5000)
    expect(after.events).toEqual(BODY.events)
    expect(after.fetchedAt).toBe(NOW)
    expect(after.problem).toBe('reconnect_required')
  })

  it('refreshes today and tomorrow — tomorrow is for the evening shutdown', () => {
    expect(RANGE.from).toBe(TODAY)
    expect(new Date(RANGE.to).getDate()).toBe(13)
  })
})

describe('parseCache', () => {
  it('reads anything unreadable as an empty cache, and drops malformed events', () => {
    expect(parseCache(undefined)).toEqual(EMPTY_CACHE)
    expect(parseCache('nonsense')).toEqual(EMPTY_CACHE)
    const parsed = parseCache({
      events: [BODY.events[0], { id: 'broken' }, { id: 'x', title: 'y', allDay: true, busy: true }],
      fetchedAt: NOW,
      rangeStart: RANGE.from,
      rangeEnd: RANGE.to,
      lastAttemptAt: NOW,
      problem: 'not-a-problem',
    })
    expect(parsed.events).toEqual([BODY.events[0]])
    expect(parsed.problem).toBeNull()
  })
})
