/**
 * Part C2's notification hook. The evening shutdown is "triggered by the
 * day's first notification slot (Decision 6), default 8pm, configurable."
 *
 * Real push needs the Cloudflare Worker, VAPID keys, and the cron sender
 * from Part H3 — none of which exist yet. So this file is the contract
 * both halves share: the slot itself (what H3 will send, and where it
 * deep-links), and the pure rule for when it's due. Today surfaces it
 * in-app from that time on, which is also exactly what H3's DoD asks for
 * when notification permission is denied ("degrades gracefully with
 * in-app surfacing instead").
 */
/**
 * Decision 6's first slot, highest priority. Part H3's sender budgets it
 * against the two-per-day cap; `route` is the notification's deep link.
 */
export const EVENING_SHUTDOWN_SLOT = {
  id: 'evening-shutdown',
  priority: 1,
  route: '/shutdown',
  title: 'Evening shutdown',
  body: "Look back at today and pick tomorrow's three.",
} as const

export const DEFAULT_SHUTDOWN_TIME = '20:00'

const TIME_PATTERN = /^([01]\d|2[0-3]):([0-5]\d)$/

/** `HH:MM`, 24-hour — the value an `<input type="time">` produces. */
export function isValidShutdownTime(value: string): boolean {
  return TIME_PATTERN.test(value)
}

/**
 * Today's reminder instant: `time` on `now`'s local date. Built from the
 * local date's fields, so 20:00 is 20:00 on a DST day too; a time inside a
 * spring-forward gap resolves forward. An invalid `time` falls back to the
 * default rather than never firing.
 */
export function shutdownReminderAt(now: number, time: string): number {
  const match = TIME_PATTERN.exec(time) ?? TIME_PATTERN.exec(DEFAULT_SHUTDOWN_TIME)
  if (!match) throw new Error('DEFAULT_SHUTDOWN_TIME is not a valid HH:MM time')
  const d = new Date(now)
  return new Date(
    d.getFullYear(),
    d.getMonth(),
    d.getDate(),
    Number(match[1]),
    Number(match[2]),
  ).getTime()
}

/** From the reminder time until midnight, unless tonight's shutdown is already done. */
export function isShutdownDue(now: number, time: string, completedToday: boolean): boolean {
  return !completedToday && now >= shutdownReminderAt(now, time)
}
