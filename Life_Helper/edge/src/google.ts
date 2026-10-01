/**
 * The Worker's only conversation with Google: trade the stored refresh
 * token for a short-lived access token, list the primary calendar's events
 * in a range, and normalize them into the contract's shape. Read-only by
 * construction: the grant is `calendar.readonly`, and nothing here issues
 * anything but GETs to the Calendar API.
 *
 * `fetcher` is injected so tests exercise every branch against canned
 * Google responses without a network.
 */
import type { CalendarEvent, EdgeErrorCode } from './contract.js'

export const CALENDAR_SCOPE = 'https://www.googleapis.com/auth/calendar.readonly'
const TOKEN_URL = 'https://oauth2.googleapis.com/token'
const EVENTS_URL = 'https://www.googleapis.com/calendar/v3/calendars/primary/events'
// Two days of one person's calendar is far below one page; the cap only
// stops a pathological calendar from turning one request into dozens.
const MAX_PAGES = 4

export class EdgeError extends Error {
  readonly code: EdgeErrorCode
  readonly status: number

  constructor(code: EdgeErrorCode, status: number) {
    super(code)
    this.code = code
    this.status = status
  }
}

export interface GoogleCredentials {
  readonly clientId: string
  readonly clientSecret: string
  readonly refreshToken: string
}

/**
 * A fresh access token for every request, deliberately — no cache. A
 * cache would live in an isolate that Cloudflare recycles at will, and at
 * a few dozen requests a day the extra token call costs nothing that
 * Decision 11 measures (it isn't Calendar API quota, and the time spent
 * awaiting it isn't Worker CPU time).
 */
export async function getAccessToken(
  credentials: GoogleCredentials,
  fetcher: typeof fetch,
): Promise<string> {
  let response: Response
  try {
    response = await fetcher(TOKEN_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({
        grant_type: 'refresh_token',
        refresh_token: credentials.refreshToken,
        client_id: credentials.clientId,
        client_secret: credentials.clientSecret,
      }),
    })
  } catch {
    throw new EdgeError('upstream_error', 502)
  }

  if (!response.ok) {
    // invalid_grant is Google's answer for a revoked, expired, or
    // password-reset-invalidated refresh token: only reconnecting fixes it.
    // Anything else (a 5xx, a malformed client) might pass on a retry.
    const body = (await response.json().catch(() => ({}))) as { error?: string }
    if (body.error === 'invalid_grant') throw new EdgeError('reconnect_required', 403)
    throw new EdgeError('upstream_error', 502)
  }

  const body = (await response.json()) as { access_token?: string; scope?: string }
  if (!body.access_token) throw new EdgeError('upstream_error', 502)
  // Google's consent screen lets the user untick individual scopes. A grant
  // that no longer includes calendar access is as good as revoked.
  if (body.scope !== undefined && !body.scope.split(' ').includes(CALENDAR_SCOPE)) {
    throw new EdgeError('reconnect_required', 403)
  }
  return body.access_token
}

interface GoogleEventTime {
  readonly date?: string
  readonly dateTime?: string
}

interface GoogleEvent {
  readonly id?: string
  readonly summary?: string
  readonly status?: string
  readonly transparency?: string
  readonly start?: GoogleEventTime
  readonly end?: GoogleEventTime
}

/** Google's event → the contract's, or null for anything that isn't a real, placed event. */
export function normalizeEvent(event: GoogleEvent): CalendarEvent | null {
  if (event.status === 'cancelled' || !event.id || !event.start || !event.end) return null
  const summary = event.summary?.trim()
  const title = summary !== undefined && summary.length > 0 ? summary : 'Untitled event'
  const busy = event.transparency !== 'transparent'

  if (event.start.date && event.end.date) {
    return {
      id: event.id,
      title,
      allDay: true,
      startDate: event.start.date,
      endDate: event.end.date,
      busy,
    }
  }
  if (event.start.dateTime && event.end.dateTime) {
    const start = Date.parse(event.start.dateTime)
    const end = Date.parse(event.end.dateTime)
    if (!Number.isFinite(start) || !Number.isFinite(end)) return null
    return { id: event.id, title, allDay: false, start, end, busy }
  }
  return null
}

/**
 * Every event overlapping [from, to), recurring ones expanded into their
 * individual occurrences (`singleEvents=true`), in start order. `fields`
 * keeps the response to the handful of properties normalizeEvent reads —
 * attendees, descriptions, and locations never leave Google at all.
 */
export async function listEvents(
  accessToken: string,
  from: number,
  to: number,
  fetcher: typeof fetch,
): Promise<CalendarEvent[]> {
  const events: CalendarEvent[] = []
  let pageToken: string | undefined

  for (let page = 0; page < MAX_PAGES; page++) {
    const url = new URL(EVENTS_URL)
    url.searchParams.set('timeMin', new Date(from).toISOString())
    url.searchParams.set('timeMax', new Date(to).toISOString())
    url.searchParams.set('singleEvents', 'true')
    url.searchParams.set('orderBy', 'startTime')
    url.searchParams.set('maxResults', '250')
    url.searchParams.set(
      'fields',
      'nextPageToken,items(id,summary,status,transparency,start(date,dateTime),end(date,dateTime))',
    )
    if (pageToken) url.searchParams.set('pageToken', pageToken)

    let response: Response
    try {
      response = await fetcher(url.toString(), {
        headers: { Authorization: `Bearer ${accessToken}` },
      })
    } catch {
      throw new EdgeError('upstream_error', 502)
    }

    if (response.status === 401) throw new EdgeError('reconnect_required', 403)
    if (response.status === 403) {
      // A 403 is either a narrowed grant (reconnecting fixes it) or the
      // Calendar API not being enabled on the project (it doesn't).
      const text = await response.text().catch(() => '')
      if (/insufficientPermissions|ACCESS_TOKEN_SCOPE_INSUFFICIENT/.test(text)) {
        throw new EdgeError('reconnect_required', 403)
      }
      throw new EdgeError('upstream_error', 502)
    }
    if (!response.ok) throw new EdgeError('upstream_error', 502)

    const body = (await response.json()) as { items?: GoogleEvent[]; nextPageToken?: string }
    for (const item of body.items ?? []) {
      const event = normalizeEvent(item)
      if (event) events.push(event)
    }
    pageToken = body.nextPageToken
    if (!pageToken) break
  }

  return events
}
