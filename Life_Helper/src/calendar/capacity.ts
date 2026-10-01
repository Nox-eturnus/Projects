/**
 * Part C3's capacity: "waking hours minus events minus a configurable
 * buffer, displayed on Today as available minutes," compared against the
 * top 3's estimates. Pure and synchronous, like every other rule in this
 * app, so it's tested without a calendar.
 *
 * Choices the plan leaves open, each documented in
 * docs/phase_C3_calendar.md:
 *
 * - **Remaining, not whole-day.** Today's capacity counts from now (or
 *   from waking, whichever is later) to the end of waking hours. At 6pm,
 *   "you had 9 hours today" is no use for deciding what fits.
 * - **The buffer shrinks with the day.** It's the slack for everything a
 *   calendar doesn't show — meals, travel, context switches — and a day
 *   that's three-quarters gone needs only a quarter of it.
 * - **Only busy, timed events count.** All-day events (birthdays,
 *   holidays, "out of office" banners) and events marked "free" don't
 *   take time. Overlapping events count once.
 */
import type { CalendarEvent, TimedEvent } from '../../edge/src/contract.js'
import { addLocalDays, localDayKey, startOfNextLocalDay } from '../scheduling/localDay.js'

export interface CapacitySettings {
  /** `HH:MM`, 24-hour. */
  readonly wakeStart: string
  /** `HH:MM`; earlier than wakeStart means past midnight (a 01:00 bedtime). */
  readonly wakeEnd: string
  readonly bufferMinutes: number
}

export const DEFAULT_CAPACITY_SETTINGS: CapacitySettings = {
  wakeStart: '07:00',
  wakeEnd: '23:00',
  bufferMinutes: 60,
}

export interface Capacity {
  /** Waking minutes left in the day (from now, or from waking up). */
  readonly remainingMinutes: number
  readonly busyMinutes: number
  readonly bufferMinutes: number
  readonly freeMinutes: number
  /** When the waking window closes. */
  readonly windowEnd: number
  /** Past the end of waking hours: nothing left to plan. */
  readonly dayOver: boolean
}

const MINUTE_MS = 60_000
const TIME_PATTERN = /^([01]\d|2[0-3]):([0-5]\d)$/

export function isValidTime(value: string): boolean {
  return TIME_PATTERN.test(value)
}

function atTime(dayStart: number, time: string, fallback: string): number {
  const match = TIME_PATTERN.exec(time) ?? TIME_PATTERN.exec(fallback)
  const d = new Date(dayStart)
  return new Date(
    d.getFullYear(),
    d.getMonth(),
    d.getDate(),
    Number(match?.[1] ?? 0),
    Number(match?.[2] ?? 0),
  ).getTime()
}

/** The waking window for the day starting at `dayStart`, built from local date fields (DST-safe). */
export function wakingWindow(
  dayStart: number,
  settings: CapacitySettings,
): { start: number; end: number } {
  const start = atTime(dayStart, settings.wakeStart, DEFAULT_CAPACITY_SETTINGS.wakeStart)
  let end = atTime(dayStart, settings.wakeEnd, DEFAULT_CAPACITY_SETTINGS.wakeEnd)
  if (end <= start) {
    end = atTime(addLocalDays(dayStart, 1), settings.wakeEnd, DEFAULT_CAPACITY_SETTINGS.wakeEnd)
  }
  return { start, end }
}

/**
 * The events that are on the day starting at `dayStart`: timed ones that
 * overlap it, and all-day ones whose dates include it. All-day dates are
 * compared as `YYYY-MM-DD` strings, which sort correctly and don't depend
 * on any timezone.
 */
export function eventsOnDay(events: readonly CalendarEvent[], dayStart: number): CalendarEvent[] {
  const dayEnd = startOfNextLocalDay(dayStart)
  const key = localDayKey(dayStart)
  return events
    .filter((event) =>
      event.allDay
        ? event.startDate <= key && key < event.endDate
        : event.start < dayEnd && event.end > dayStart,
    )
    .sort((a, b) => {
      if (a.allDay !== b.allDay) return a.allDay ? -1 : 1
      return a.allDay || b.allDay ? 0 : a.start - b.start
    })
}

/** Total length of the union of [start, end) intervals, each clipped to [from, to). */
function busyWithin(events: readonly TimedEvent[], from: number, to: number): number {
  const intervals = events
    .map((event) => [Math.max(event.start, from), Math.min(event.end, to)] as const)
    .filter(([start, end]) => end > start)
    .sort((a, b) => a[0] - b[0])
  let total = 0
  let currentStart = -Infinity
  let currentEnd = -Infinity
  for (const [start, end] of intervals) {
    if (start > currentEnd) {
      if (currentEnd > currentStart) total += currentEnd - currentStart
      currentStart = start
      currentEnd = end
    } else {
      currentEnd = Math.max(currentEnd, end)
    }
  }
  if (currentEnd > currentStart) total += currentEnd - currentStart
  return total
}

export function computeCapacity(
  events: readonly CalendarEvent[],
  dayStart: number,
  now: number,
  settings: CapacitySettings,
): Capacity {
  const window = wakingWindow(dayStart, settings)
  const from = Math.max(now, window.start)
  if (from >= window.end) {
    return {
      remainingMinutes: 0,
      busyMinutes: 0,
      bufferMinutes: 0,
      freeMinutes: 0,
      windowEnd: window.end,
      dayOver: true,
    }
  }

  const timedBusy = events.filter((event): event is TimedEvent => !event.allDay && event.busy)
  const remaining = window.end - from
  const busy = busyWithin(timedBusy, from, window.end)
  const buffer =
    Math.max(0, settings.bufferMinutes) * MINUTE_MS * (remaining / (window.end - window.start))
  const free = Math.max(0, remaining - busy - buffer)

  return {
    remainingMinutes: Math.floor(remaining / MINUTE_MS),
    busyMinutes: Math.round(busy / MINUTE_MS),
    bufferMinutes: Math.round(buffer / MINUTE_MS),
    freeMinutes: Math.floor(free / MINUTE_MS),
    windowEnd: window.end,
    dayOver: false,
  }
}

export interface Commitment {
  /** Sum of the estimates that exist. */
  readonly estimatedMinutes: number
  readonly estimatedCount: number
  /** Open tasks without an estimate — the sum can only understate the commitment. */
  readonly unestimatedCount: number
}

/** The open tasks' estimates, added up. Finished tasks no longer need time. */
export function commitmentOf(
  tasks: readonly { readonly estimate_min: number | null; readonly completed_at: number | null }[],
): Commitment {
  const open = tasks.filter((task) => task.completed_at === null)
  const estimated = open.filter((task) => task.estimate_min !== null && task.estimate_min > 0)
  return {
    estimatedMinutes: estimated.reduce((sum, task) => sum + (task.estimate_min ?? 0), 0),
    estimatedCount: estimated.length,
    unestimatedCount: open.length - estimated.length,
  }
}

/** "4h 20m", "45m", "2h". */
export function formatMinutes(minutes: number): string {
  const whole = Math.max(0, Math.round(minutes))
  const hours = Math.floor(whole / 60)
  const rest = whole % 60
  if (hours === 0) return `${String(rest)}m`
  if (rest === 0) return `${String(hours)}h`
  return `${String(hours)}h ${String(rest)}m`
}
