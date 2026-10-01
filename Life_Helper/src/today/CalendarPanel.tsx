import type { CalendarEvent } from '../../edge/src/contract.js'
import { eventsOnDay } from '../calendar/capacity.js'
import type { CalendarProblem } from '../calendar/calendarStore.js'
import { coversDay } from '../calendar/calendarSync.js'
import type { CalendarState } from '../calendar/useCalendar.js'
import { Button } from '../ui/Button.js'
import { Link } from '../ui/router.js'
import { formatAsOf, formatSince, formatTime } from './labels.js'
import styles from './CalendarPanel.module.css'

/** After this, the "updated" line changes from a quiet note to an explicit "as of". */
const STALE_AFTER_MS = 30 * 60 * 1000

function eventTime(event: CalendarEvent): string {
  if (event.allDay) return 'All day'
  const start = formatTime(event.start) ?? '12:00 AM'
  const end = formatTime(event.end) ?? '12:00 AM'
  return `${start} – ${end}`
}

/**
 * The problems that need the user to do something — each says what, in
 * plain words. Offline and upstream errors aren't here: those just make
 * the calendar stale, and the freshness line says so.
 */
function ProblemNote({ problem }: { problem: CalendarProblem }) {
  switch (problem) {
    case 'reconnect_required':
      return (
        <p className={styles.problem} role="status">
          Google Calendar needs reconnecting — access was revoked or has expired. On your computer,
          run <code>pnpm calendar:connect</code> in the Life_Helper folder.
        </p>
      )
    case 'unauthorized':
      return (
        <p className={styles.problem} role="status">
          This device&apos;s calendar key wasn&apos;t accepted.{' '}
          <Link to="/settings">Check it in Settings</Link>.
        </p>
      )
    case 'not_configured':
      return (
        <p className={styles.problem} role="status">
          The calendar Worker is missing part of its setup. Finish the steps in{' '}
          <code>docs/phase_C3_calendar.md</code> on your computer.
        </p>
      )
    case 'offline':
    case 'upstream_error':
      return null
  }
}

/**
 * Today's calendar (Part C3): the day's events, rendered from the local
 * cache — so they're there offline — with a freshness line that always
 * says how old they are, and says so plainly once they're stale or the
 * last refresh failed.
 */
export function CalendarPanel({
  calendar,
  dayStart,
  now,
}: {
  calendar: CalendarState
  dayStart: number
  now: number
}) {
  const { cache, refreshing, refreshNow } = calendar
  const hasToday = coversDay(cache, dayStart)
  const events = hasToday ? eventsOnDay(cache.events, dayStart) : []

  let freshness: string
  if (cache.fetchedAt === null) {
    freshness = refreshing ? 'Loading your calendar…' : 'Not loaded yet.'
  } else {
    const asOf = formatAsOf(cache.fetchedAt, now)
    const stale = now - cache.fetchedAt > STALE_AFTER_MS
    if (cache.problem === 'offline') freshness = `Offline — calendar as of ${asOf}.`
    else if (cache.problem !== null) freshness = `Couldn't refresh — calendar as of ${asOf}.`
    else
      freshness = stale
        ? `Calendar as of ${asOf}.`
        : `Updated ${formatSince(cache.fetchedAt, now)}.`
  }

  return (
    <section className={styles.panel} aria-labelledby="calendar-heading">
      <h2 id="calendar-heading" className={styles.title}>
        Calendar
      </h2>

      {cache.problem ? <ProblemNote problem={cache.problem} /> : null}

      {hasToday ? (
        events.length > 0 ? (
          <ul className={styles.events}>
            {events.map((event) => (
              <li key={event.id} className={styles.event}>
                <span className={styles.time}>{eventTime(event)}</span>
                <span className={styles.eventTitle}>
                  {event.title}
                  {event.busy ? null : <span className={styles.free}> (free)</span>}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className={styles.note}>Nothing on your calendar today.</p>
        )
      ) : null}

      <div className={styles.freshness}>
        <span aria-live="polite">
          {refreshing && cache.fetchedAt !== null ? 'Refreshing…' : freshness}
        </span>
        <Button variant="ghost" size="sm" onClick={refreshNow} disabled={refreshing}>
          Refresh
        </Button>
      </div>
    </section>
  )
}
