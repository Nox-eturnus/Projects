/**
 * Calendar-day arithmetic in the device's local timezone — the one place
 * Part C1's scheduling model turns an instant (every date column is a
 * millisecond epoch) into "which day is this?"
 *
 * Every function here goes through the local `Date` fields (year, month,
 * date) rather than dividing by 86,400,000. A local day is not always 24
 * hours long — a DST transition makes one 23 hours and another 25 — and
 * a non-UTC offset means UTC day boundaries aren't local day boundaries
 * at all (in IST, 03:00 and 07:00 on the same local day fall on two
 * different UTC days). Epoch-millisecond division gets both wrong;
 * `Date`'s local fields get both right, which is what localDay.test.ts
 * checks under real DST zones.
 */

/** The first instant of `ms`'s local calendar day. */
export function startOfLocalDay(ms: number): number {
  const d = new Date(ms)
  // Built from fields rather than setHours(0, 0, 0, 0) on `d`: in a zone
  // whose DST starts at midnight (e.g. America/Sao_Paulo before 2019),
  // 00:00 doesn't exist that day and both forms resolve forward to 01:00,
  // but this form makes it explicit the result is "that day's first
  // instant," never a neighbouring day's.
  return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()
}

/**
 * Same wall-clock time, `days` local calendar days later (negative for
 * earlier). Across a DST boundary the elapsed time is 23 or 25 hours, not
 * 24 — "tomorrow at 9am" stays at 9am.
 */
export function addLocalDays(ms: number, days: number): number {
  const d = new Date(ms)
  d.setDate(d.getDate() + days)
  return d.getTime()
}

/** The first instant of the local calendar day after `ms`'s. */
export function startOfNextLocalDay(ms: number): number {
  const d = new Date(ms)
  return new Date(d.getFullYear(), d.getMonth(), d.getDate() + 1).getTime()
}

/**
 * An integer that orders local calendar days: YYYYMMDD. Two instants on
 * the same local day share one ordinal regardless of time or DST; a later
 * day always has a larger one.
 */
export function localDayOrdinal(ms: number): number {
  const d = new Date(ms)
  return d.getFullYear() * 10_000 + (d.getMonth() + 1) * 100 + d.getDate()
}

/** Negative if `a` is on an earlier local day than `b`, 0 if the same day, positive if later. */
export function compareLocalDays(a: number, b: number): number {
  return localDayOrdinal(a) - localDayOrdinal(b)
}
