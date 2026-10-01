/**
 * The shape of `GET /calendar/events` — the one thing the edge Worker and
 * the app both depend on. Types only, so the app's `import type` of this
 * file is erased at build time and none of the Worker ends up in the
 * client bundle.
 *
 * Events are normalized here rather than passed through from Google: the
 * app should never need to know which calendar provider is behind the
 * Worker (Decision 11's "migrating the Worker is a weekend" depends on
 * exactly that), and a timed event and an all-day one mean genuinely
 * different things for capacity, so they're different variants.
 */

/** A timed event: an instant range, epoch milliseconds. */
export interface TimedEvent {
  readonly id: string
  readonly title: string
  readonly allDay: false
  readonly start: number
  readonly end: number
  /** False for events marked "free" in the calendar — they don't use up capacity. */
  readonly busy: boolean
}

/**
 * An all-day event: calendar dates, not instants — a birthday on the 12th
 * is on the 12th in whatever timezone the device is in. `endDate` is
 * exclusive, as in Google's API and iCalendar.
 */
export interface AllDayEvent {
  readonly id: string
  readonly title: string
  readonly allDay: true
  readonly startDate: string
  readonly endDate: string
  readonly busy: boolean
}

export type CalendarEvent = TimedEvent | AllDayEvent

export interface EventsResponse {
  readonly events: readonly CalendarEvent[]
  /** When the Worker fetched these from the provider, epoch ms. */
  readonly fetchedAt: number
}

/**
 * Every failure the app needs to tell apart, because each one asks the
 * user for something different:
 *
 * - `unauthorized` — this device's key is wrong or missing (fix it in
 *   Settings).
 * - `reconnect_required` — Google no longer accepts the stored grant:
 *   revoked, expired, or consent narrowed (run the connect script again).
 * - `not_configured` — the Worker is missing a secret (finish setup).
 * - `bad_request`, `not_found` — the app asked for something invalid.
 * - `upstream_error` — Google failed in a way retrying may fix.
 */
export type EdgeErrorCode =
  | 'unauthorized'
  | 'reconnect_required'
  | 'not_configured'
  | 'bad_request'
  | 'not_found'
  | 'upstream_error'

export interface EdgeErrorBody {
  readonly error: EdgeErrorCode
}
