/**
 * Part C2's fallback when the evening shutdown didn't happen: Today proposes
 * three "drawn from due today, then slipping, then oldest scheduled," and
 * the user accepts or swaps with one tap. The shutdown's own pick step uses
 * the same ranking for tomorrow, so the two never disagree about what's
 * most worth doing.
 *
 * Pure and synchronous over already-queried rows (see DAY_TASKS_SQL), so
 * the ranking is tested without a database.
 */
import { startOfNextLocalDay } from '../scheduling/localDay.js'

/** One row of DAY_TASKS_SQL. */
export interface DayTask {
  readonly id: string
  readonly title: string
  readonly status: string | null
  readonly created_at: number
  readonly due_at: number | null
  readonly scheduled_for: number | null
  readonly defer_until: number | null
  readonly touch_count: number
  readonly last_touched_at: number | null
  readonly completed_at: number | null
}

/**
 * Why a task is a candidate for a day — shown under it so a proposal reads
 * as reasoned rather than arbitrary. Deliberately no "overdue" or
 * "slipping" wording anywhere a user sees it (Decision 7).
 */
export type CandidateReason = 'due' | 'carriedOver' | 'scheduled'

export interface Candidate {
  readonly task: DayTask
  readonly reason: CandidateReason
}

function byNumbers(...keys: ((task: DayTask) => number)[]) {
  return (a: DayTask, b: DayTask): number => {
    for (const key of keys) {
      const diff = key(a) - key(b)
      if (diff !== 0) return diff
    }
    return a.id < b.id ? -1 : a.id > b.id ? 1 : 0
  }
}

/**
 * Every open task worth doing on the day starting at `dayStart`, best
 * first, each at most once (under the first bucket it qualifies for):
 *
 * 1. **Due** by the end of the day — a real deadline, including one that
 *    has already passed. Earliest deadline first.
 * 2. **Carried over** — the plan's "slipping": rescheduled at least once
 *    (`touch_count` > 0) or scheduled for an earlier day and not done.
 *    Most-rescheduled first, then longest untouched — Part C4's own
 *    ordering ("touch count first and age second"). A task deliberately
 *    scheduled for a *later* day isn't carried over, however often it was
 *    moved: that move was the plan.
 * 3. **Scheduled** for this day. Oldest task first.
 *
 * Tasks with no date that were never moved aren't candidates: nothing says
 * they belong to this day.
 */
export function rankCandidates(tasks: readonly DayTask[], dayStart: number): Candidate[] {
  const dayEnd = startOfNextLocalDay(dayStart)
  const open = tasks.filter((task) => task.completed_at === null)

  const due = open
    .filter((task) => task.due_at !== null && task.due_at < dayEnd)
    .sort(
      byNumbers(
        (task) => task.due_at ?? 0,
        (task) => task.created_at,
      ),
    )

  const carriedOver = open
    .filter((task) => {
      const notPlannedLater = task.scheduled_for === null || task.scheduled_for < dayEnd
      const missedItsDay = task.scheduled_for !== null && task.scheduled_for < dayStart
      return notPlannedLater && (task.touch_count > 0 || missedItsDay)
    })
    .sort(
      byNumbers(
        (task) => -task.touch_count,
        (task) => task.last_touched_at ?? task.created_at,
        (task) => task.created_at,
      ),
    )

  const scheduled = open
    .filter(
      (task) =>
        task.scheduled_for !== null &&
        task.scheduled_for >= dayStart &&
        task.scheduled_for < dayEnd,
    )
    .sort(
      byNumbers(
        (task) => task.created_at,
        (task) => task.scheduled_for ?? 0,
      ),
    )

  const seen = new Set<string>()
  const ranked: Candidate[] = []
  const buckets: [readonly DayTask[], CandidateReason][] = [
    [due, 'due'],
    [carriedOver, 'carriedOver'],
    [scheduled, 'scheduled'],
  ]
  for (const [bucket, reason] of buckets) {
    for (const task of bucket) {
      if (seen.has(task.id)) continue
      seen.add(task.id)
      ranked.push({ task, reason })
    }
  }
  return ranked
}

/**
 * The first three candidates not in `excluded` — the proposal, and what a
 * swap draws its replacement from (swapping adds the swapped task to
 * `excluded`, so the next candidate in line moves up).
 */
export function proposeTop3(
  tasks: readonly DayTask[],
  dayStart: number,
  excluded: ReadonlySet<string> = new Set(),
): Candidate[] {
  return rankCandidates(tasks, dayStart)
    .filter((candidate) => !excluded.has(candidate.task.id))
    .slice(0, 3)
}
