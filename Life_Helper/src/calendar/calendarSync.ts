/**
 * Refreshing the calendar cache from the edge Worker. Part C3's cadence:
 * "on app focus and at most every 15 minutes, never on a background
 * timer." So there is no timer here at all — a refresh is only ever
 * *attempted* when the app is opened, refocused, or comes back online
 * (useCalendar wires those up), and an attempt within 15 minutes of the
 * last one does nothing. At that cadence the Worker and Calendar API see a
 * few dozen requests a day.
 *
 * A failed refresh keeps the events already cached: Today goes on showing
 * the last known calendar, marked stale, rather than going blank.
 */
import type { EdgeErrorBody, EventsResponse } from '../../edge/src/contract.js'
import { startOfLocalDay, startOfNextLocalDay } from '../scheduling/localDay.js'
import type { CalendarCache, CalendarConnection, CalendarProblem } from './calendarStore.js'

export const REFRESH_INTERVAL_MS = 15 * 60 * 1000
const REQUEST_TIMEOUT_MS = 15_000

export type FetchResult =
  | { readonly ok: true; readonly body: EventsResponse }
  | { readonly ok: false; readonly problem: CalendarProblem }

function isEventsResponse(value: unknown): value is EventsResponse {
  return (
    typeof value === 'object' &&
    value !== null &&
    Array.isArray((value as { events?: unknown }).events) &&
    typeof (value as { fetchedAt?: unknown }).fetchedAt === 'number'
  )
}

export async function fetchEvents(
  connection: CalendarConnection,
  range: { from: number; to: number },
  fetcher: typeof fetch = fetch,
): Promise<FetchResult> {
  const url = new URL('/calendar/events', connection.edgeUrl.trim())
  url.searchParams.set('from', String(range.from))
  url.searchParams.set('to', String(range.to))

  let response: Response
  try {
    response = await fetcher(url.toString(), {
      headers: { Authorization: `Bearer ${connection.deviceKey.trim()}` },
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    })
  } catch {
    // No answer at all: offline, DNS, a timeout, or a Worker URL that
    // doesn't exist. From the user's side these are all "couldn't reach it."
    return { ok: false, problem: 'offline' }
  }

  if (response.ok) {
    const body: unknown = await response.json().catch(() => null)
    return isEventsResponse(body) ? { ok: true, body } : { ok: false, problem: 'upstream_error' }
  }

  const body = (await response.json().catch(() => ({}))) as Partial<EdgeErrorBody>
  switch (body.error) {
    case 'unauthorized':
    case 'reconnect_required':
    case 'not_configured':
      return { ok: false, problem: body.error }
    default:
      return { ok: false, problem: response.status === 401 ? 'unauthorized' : 'upstream_error' }
  }
}

/** What to ask the Worker for: today and tomorrow (tomorrow is for the evening shutdown). */
export function refreshRange(now: number): { from: number; to: number } {
  const today = startOfLocalDay(now)
  return { from: today, to: startOfNextLocalDay(startOfNextLocalDay(today)) }
}

/** Whether the cache holds events for the whole local day starting at `dayStart`. */
export function coversDay(cache: CalendarCache, dayStart: number): boolean {
  return (
    cache.fetchedAt !== null &&
    cache.rangeStart <= dayStart &&
    cache.rangeEnd >= startOfNextLocalDay(dayStart)
  )
}

/**
 * Throttled to one attempt per 15 minutes unless forced. A cache that
 * doesn't cover today at all (the first open of a new day, say) is retried
 * after a minute instead: there's nothing useful to show until it lands,
 * but a device that's offline shouldn't hammer the Worker on every focus.
 */
export function shouldRefresh(cache: CalendarCache, now: number, force: boolean): boolean {
  if (force) return true
  if (!coversDay(cache, startOfLocalDay(now))) return now - cache.lastAttemptAt >= 60_000
  return now - cache.lastAttemptAt >= REFRESH_INTERVAL_MS
}

/** The cache after an attempt: replaced on success; on failure, same events, new problem. */
export function nextCache(
  cache: CalendarCache,
  result: FetchResult,
  range: { from: number; to: number },
  now: number,
): CalendarCache {
  if (result.ok) {
    return {
      events: result.body.events,
      fetchedAt: result.body.fetchedAt,
      rangeStart: range.from,
      rangeEnd: range.to,
      lastAttemptAt: now,
      problem: null,
    }
  }
  return { ...cache, lastAttemptAt: now, problem: result.problem }
}
