/**
 * Part C4's slipping detection — the one definition of "slipping," shared
 * by the Revisit view and by Today's proposal (whose "carried over" bucket
 * is exactly this set, in exactly this order), so the two can never
 * disagree about which tasks keep getting away.
 *
 * A task is slipping on a day when it's open and not planned for a later
 * day, and either:
 *
 * - it has been rescheduled or deferred at least once (C1's
 *   `touch_count` > 0), or
 * - it was scheduled for an earlier day and that day passed.
 *
 * A task deliberately scheduled for a *later* day isn't slipping, however
 * often it was moved: that move was the plan. Someday, deferred, archived,
 * and deleted tasks never reach this code — the queries exclude them.
 *
 * Ranked by touch count first and age second (the plan: "a task deferred
 * four times is a stronger signal than a task that has sat untouched for
 * twelve days"). Age is how long since it was last touched — or created,
 * if it never was — so of two equally-moved tasks, the one left alone
 * longer comes first.
 *
 * Pure and synchronous over already-queried rows, like proposal.ts.
 */
import { startOfNextLocalDay } from '../scheduling/localDay.js'
import type { DayTask } from '../today/proposal.js'

export function isSlipping(task: DayTask, dayStart: number): boolean {
  if (task.completed_at !== null) return false
  const notPlannedLater =
    task.scheduled_for === null || task.scheduled_for < startOfNextLocalDay(dayStart)
  const missedItsDay = task.scheduled_for !== null && task.scheduled_for < dayStart
  return notPlannedLater && (task.touch_count > 0 || missedItsDay)
}

/** Most-moved first; then longest untouched; then oldest; then by id, so the order is total. */
export function compareSlipping(a: DayTask, b: DayTask): number {
  return (
    b.touch_count - a.touch_count ||
    (a.last_touched_at ?? a.created_at) - (b.last_touched_at ?? b.created_at) ||
    a.created_at - b.created_at ||
    (a.id < b.id ? -1 : a.id > b.id ? 1 : 0)
  )
}

/**
 * Every task slipping on the day starting at `dayStart`, ranked. Tasks in
 * `excluded` — the day's committed top 3 — are left out: they're already
 * what "do it now" would make them.
 */
export function findSlipping<T extends DayTask>(
  tasks: readonly T[],
  dayStart: number,
  excluded: ReadonlySet<string> = new Set(),
): T[] {
  return tasks
    .filter((task) => !excluded.has(task.id) && isSlipping(task, dayStart))
    .sort(compareSlipping)
}
