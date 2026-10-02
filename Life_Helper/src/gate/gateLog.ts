/**
 * Part C6's measurements that no table already holds: how long Today took
 * to appear on each cold start, which days the app was opened, and how
 * every calendar refresh went. Per device, in localStorage — they describe
 * this device's experience, not the user's data, and they mustn't sync.
 *
 * Each log is bounded (newest kept), so it can't grow without limit, and
 * every read tolerates missing or malformed storage.
 */
import type { CalendarProblem } from '../calendar/calendarStore.js'
import { readLocal, writeLocal } from '../lib/localStore.js'
import { localDayKey } from '../scheduling/localDay.js'

export const COLD_STARTS_KEY = 'life-helper-gate-cold-starts'
export const OPEN_DAYS_KEY = 'life-helper-gate-open-days'
export const CALENDAR_HEALTH_KEY = 'life-helper-gate-calendar-health'

const MAX_COLD_STARTS = 30
const MAX_DAYS = 60

// --- The device -------------------------------------------------------------

export interface DeviceInfo {
  readonly android: boolean
  readonly mobile: boolean
}

export function deviceInfo(userAgent: string = navigator.userAgent): DeviceInfo {
  const android = /Android/i.test(userAgent)
  return { android, mobile: android || /iPhone|iPad|Mobile/i.test(userAgent) }
}

// --- Cold starts ------------------------------------------------------------

export interface ColdStart {
  /** When it was recorded. */
  readonly at: number
  /** Navigation start → Today rendered with its data, in ms. */
  readonly ms: number
  readonly android: boolean
}

function isColdStart(value: unknown): value is ColdStart {
  const v = value as Partial<ColdStart> | null
  return (
    typeof v === 'object' &&
    v !== null &&
    typeof v.at === 'number' &&
    typeof v.ms === 'number' &&
    Number.isFinite(v.ms) &&
    typeof v.android === 'boolean'
  )
}

export function parseColdStarts(value: unknown): ColdStart[] {
  return Array.isArray(value) ? value.filter(isColdStart) : []
}

export function readColdStarts(): ColdStart[] {
  return readLocal(COLD_STARTS_KEY, parseColdStarts)
}

export function recordColdStart(sample: ColdStart): void {
  writeLocal(COLD_STARTS_KEY, [...readColdStarts(), sample].slice(-MAX_COLD_STARTS))
}

// --- Days the app was opened ---------------------------------------------------

export function parseOpenDays(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((day): day is string => typeof day === 'string') : []
}

export function readOpenDays(): string[] {
  return readLocal(OPEN_DAYS_KEY, parseOpenDays)
}

/** Once per day is enough: "opened" is a yes/no per day. */
export function recordOpen(now: number): void {
  const days = readOpenDays()
  const today = localDayKey(now)
  if (days.at(-1) === today) return
  writeLocal(OPEN_DAYS_KEY, [...days.filter((day) => day !== today), today].slice(-MAX_DAYS))
}

// --- Calendar health ------------------------------------------------------------

export interface CalendarDay {
  /** Successful refreshes that day. */
  readonly ok: number
  /** Failed refreshes that day, by reason. */
  readonly problems: Partial<Record<CalendarProblem, number>>
}

export interface CalendarHealth {
  /** By local day key; a day with no refresh at all has no entry. */
  readonly days: Readonly<Partial<Record<string, CalendarDay>>>
  /** First and latest successful refresh — the span the token has held for. */
  readonly firstOkAt: number | null
  readonly lastOkAt: number | null
  /** The last time the connection was saved in Settings: manual intervention. */
  readonly connectionSavedAt: number | null
}

export const EMPTY_HEALTH: CalendarHealth = {
  days: {},
  firstOkAt: null,
  lastOkAt: null,
  connectionSavedAt: null,
}

const PROBLEMS: readonly CalendarProblem[] = [
  'offline',
  'unauthorized',
  'reconnect_required',
  'not_configured',
  'upstream_error',
]

function count(value: unknown): number {
  return typeof value === 'number' && Number.isInteger(value) && value >= 0 ? value : 0
}

function time(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

export function parseCalendarHealth(value: unknown): CalendarHealth {
  const v = typeof value === 'object' && value !== null ? (value as Record<string, unknown>) : {}
  const rawDays =
    typeof v.days === 'object' && v.days !== null ? (v.days as Record<string, unknown>) : {}
  const days: Record<string, CalendarDay> = {}
  for (const [key, raw] of Object.entries(rawDays)) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(key) || typeof raw !== 'object' || raw === null) continue
    const day = raw as Record<string, unknown>
    const rawProblems =
      typeof day.problems === 'object' && day.problems !== null
        ? (day.problems as Record<string, unknown>)
        : {}
    const problems: Partial<Record<CalendarProblem, number>> = {}
    for (const problem of PROBLEMS) {
      const n = count(rawProblems[problem])
      if (n > 0) problems[problem] = n
    }
    days[key] = { ok: count(day.ok), problems }
  }
  return {
    days,
    firstOkAt: time(v.firstOkAt),
    lastOkAt: time(v.lastOkAt),
    connectionSavedAt: time(v.connectionSavedAt),
  }
}

export function readCalendarHealth(): CalendarHealth {
  return readLocal(CALENDAR_HEALTH_KEY, parseCalendarHealth)
}

/** Keeps only the newest MAX_DAYS days. */
function trimDays(
  days: Readonly<Partial<Record<string, CalendarDay>>>,
): Partial<Record<string, CalendarDay>> {
  const keys = Object.keys(days).sort().slice(-MAX_DAYS)
  return Object.fromEntries(keys.map((key) => [key, days[key]]))
}

/** One refresh's outcome: `null` for success, else why it failed. */
export function recordCalendarRefresh(problem: CalendarProblem | null, now: number): void {
  const health = readCalendarHealth()
  const key = localDayKey(now)
  const day = health.days[key] ?? { ok: 0, problems: {} }
  const nextDay: CalendarDay =
    problem === null
      ? { ...day, ok: day.ok + 1 }
      : { ...day, problems: { ...day.problems, [problem]: (day.problems[problem] ?? 0) + 1 } }
  writeLocal(CALENDAR_HEALTH_KEY, {
    ...health,
    days: trimDays({ ...health.days, [key]: nextDay }),
    firstOkAt: problem === null ? (health.firstOkAt ?? now) : health.firstOkAt,
    lastOkAt: problem === null ? now : health.lastOkAt,
  })
}

/**
 * Saving the connection in Settings is the "manual intervention" the gate
 * counts. It also restarts the span, since the token's survival is now
 * measured from this connection.
 */
export function recordConnectionSaved(now: number): void {
  writeLocal(CALENDAR_HEALTH_KEY, {
    ...readCalendarHealth(),
    connectionSavedAt: now,
    firstOkAt: null,
    lastOkAt: null,
  })
}
