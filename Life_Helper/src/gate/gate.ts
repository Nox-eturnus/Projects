/**
 * Part C6, the Today gate: each condition evaluated from what this device
 * actually recorded — its database and its gate logs — rather than from
 * memory. Pure functions over already-read data, so each rule is tested
 * on its own; GateRoute reads the data and shows the result.
 *
 * The gate is the plan's, "fixed before execution and not negotiable
 * after": the thresholds below are its numbers, and where its wording
 * needed reading, the stricter reading is taken (see
 * docs/phase_C6_today_gate.md).
 */
import type { CalendarProblem } from '../calendar/calendarStore.js'
import { addLocalDays, localDayKey, startOfLocalDay } from '../scheduling/localDay.js'
import type { CalendarHealth, ColdStart } from './gateLog.js'

export const COLD_START_BUDGET_MS = 1500
/** One fast launch could be luck; the median of at least this many isn't. */
export const MIN_COLD_STARTS = 3
export const CALENDAR_WEEK_DAYS = 7
export const SHUTDOWN_WINDOW_DAYS = 7
export const SHUTDOWNS_NEEDED = 5
export const USAGE_STREAK_DAYS = 14

/** The problems that need the user to step in; offline and Google hiccups don't. */
export const NEEDS_YOU: readonly CalendarProblem[] = [
  'unauthorized',
  'reconnect_required',
  'not_configured',
]

export interface Verdict {
  readonly passed: boolean
  /** One line of evidence, for the report and the usage log. */
  readonly evidence: string
}

/** The local day keys from `days` before `dayStart` through it, oldest first. */
export function lastDays(dayStart: number, days: number): string[] {
  return Array.from({ length: days }, (_, i) => localDayKey(addLocalDays(dayStart, i - days + 1)))
}

// --- 1. Cold start --------------------------------------------------------------

export function median(values: readonly number[]): number {
  const sorted = [...values].sort((a, b) => a - b)
  const mid = Math.floor(sorted.length / 2)
  return sorted.length % 2 === 1 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2
}

/** Under 1.5s, on a real Android device: the median of its recorded cold starts. */
export function evaluateColdStart(samples: readonly ColdStart[]): Verdict & {
  readonly android: readonly ColdStart[]
} {
  const android = samples.filter((sample) => sample.android)
  if (android.length < MIN_COLD_STARTS) {
    return {
      passed: false,
      android,
      evidence: `${String(android.length)} of ${String(MIN_COLD_STARTS)} Android cold starts recorded so far`,
    }
  }
  const ms = android.map((sample) => sample.ms)
  const mid = Math.round(median(ms))
  return {
    passed: mid < COLD_START_BUDGET_MS,
    android,
    evidence: `median ${String(mid)}ms over ${String(android.length)} Android cold starts (slowest ${String(Math.round(Math.max(...ms)))}ms; budget ${String(COLD_START_BUDGET_MS)}ms)`,
  }
}

// --- 2. Calendar sync -------------------------------------------------------------

/**
 * "Calendar sync survives a full week without manual intervention": a
 * successful refresh at least 7 local days after the first one on the
 * current connection, and nothing in between that needed the user
 * (re-entering the key resets the span — see recordConnectionSaved()).
 */
export function evaluateCalendar(health: CalendarHealth, connected: boolean): Verdict {
  if (!connected) return { passed: false, evidence: 'not connected on this device' }
  const { firstOkAt, lastOkAt } = health
  if (firstOkAt === null || lastOkAt === null) {
    return { passed: false, evidence: 'no successful refresh recorded yet' }
  }
  const firstDay = startOfLocalDay(firstOkAt)
  const interventions = Object.entries(health.days)
    .filter(([day]) => day >= localDayKey(firstDay) && day <= localDayKey(lastOkAt))
    .flatMap(([day, record]) =>
      NEEDS_YOU.filter((problem) => (record?.problems[problem] ?? 0) > 0).map(
        (p) => `${p} on ${day}`,
      ),
    )
  if (interventions.length > 0) {
    return { passed: false, evidence: `needed you: ${interventions.join(', ')}` }
  }
  const weekLater = addLocalDays(firstDay, CALENDAR_WEEK_DAYS)
  const span = `working from ${localDayKey(firstOkAt)} to ${localDayKey(lastOkAt)}`
  return lastOkAt >= weekLater
    ? { passed: true, evidence: `${span}, no intervention` }
    : {
        passed: false,
        evidence: `${span} so far, no intervention; a week is ${localDayKey(weekLater)}`,
      }
}

// --- 3. Shutdowns -----------------------------------------------------------------

/**
 * At least 5 of 7 days. Tonight's shutdown hasn't happened yet for most
 * of the day, so the 7 days ending yesterday count too — whichever window
 * has more.
 */
export function evaluateShutdowns(shutdownDays: ReadonlySet<string>, todayStart: number): Verdict {
  const count = (end: number) =>
    lastDays(end, SHUTDOWN_WINDOW_DAYS).filter((day) => shutdownDays.has(day)).length
  const best = Math.max(count(todayStart), count(addLocalDays(todayStart, -1)))
  return {
    passed: best >= SHUTDOWNS_NEEDED,
    evidence: `${String(best)} of the last ${String(SHUTDOWN_WINDOW_DAYS)} days (needs ${String(SHUTDOWNS_NEEDED)})`,
  }
}

// --- 4. Usage ---------------------------------------------------------------------

/**
 * Consecutive days, ending today (or yesterday, if nothing's happened yet
 * today), each with at least one item captured or completed — the B4
 * gate's reading of "consecutive days meeting the Definition of used."
 */
export function currentStreak(activeDays: ReadonlySet<string>, todayStart: number): number {
  let day = activeDays.has(localDayKey(todayStart)) ? todayStart : addLocalDays(todayStart, -1)
  let streak = 0
  while (activeDays.has(localDayKey(day))) {
    streak += 1
    day = addLocalDays(day, -1)
  }
  return streak
}

export function evaluateUsage(
  activeDays: ReadonlySet<string>,
  todayStart: number,
  onPhone: boolean,
): Verdict & { readonly streak: number } {
  const streak = currentStreak(activeDays, todayStart)
  const where = onPhone ? 'on this phone' : 'on this device, which is not a phone'
  return {
    passed: onPhone && streak >= USAGE_STREAK_DAYS,
    streak,
    evidence: `${String(streak)} consecutive ${streak === 1 ? 'day' : 'days'} with something captured or completed, ${where} (needs ${String(USAGE_STREAK_DAYS)})`,
  }
}

// --- 5. Amnesty -------------------------------------------------------------------

export interface KeptSweep {
  readonly swept_at: number
  readonly item_count: number
}

/** At least one fresh start, not undone. */
export function evaluateAmnesty(sweeps: readonly KeptSweep[]): Verdict {
  const latest = sweeps.at(0)
  if (!latest) return { passed: false, evidence: 'no fresh start kept yet' }
  return {
    passed: true,
    evidence: `${String(sweeps.length)} kept; latest on ${localDayKey(latest.swept_at)}, ${String(latest.item_count)} task${latest.item_count === 1 ? '' : 's'}`,
  }
}

// --- Queries ----------------------------------------------------------------------

/**
 * Every capture and completion since `?1`, as instants: grouped into
 * local days in JS. Deleted items don't count as captures.
 */
export const GATE_ACTIVITY_SQL = `
  SELECT created_at AS at FROM items WHERE deleted_at IS NULL AND created_at >= ?1
  UNION ALL
  SELECT completed_at AS at FROM task_fields WHERE completed_at IS NOT NULL AND completed_at >= ?1
`

/** Days whose evening shutdown was completed, from `?` on. */
export const GATE_SHUTDOWNS_SQL = `
  SELECT day FROM day_plans WHERE shutdown_completed_at IS NOT NULL AND day >= ?
`

/** Fresh starts that weren't undone, newest first. */
export const GATE_SWEEPS_SQL = `
  SELECT swept_at, item_count FROM amnesty_sweeps WHERE undone_at IS NULL ORDER BY swept_at DESC
`
