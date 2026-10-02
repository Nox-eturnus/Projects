/**
 * Part C5's amnesty and someday tier (Decision 4: "everything decays").
 *
 * - A **sweep** moves every eligible task (see AMNESTY_ELIGIBLE_SQL) to
 *   someday in one action: it never deletes and never asks for a reason.
 *   The sweep is a row of its own (`amnesty_sweeps`) and each task it moved
 *   is tagged with its id, so undo restores exactly those tasks, for 24
 *   hours, across reloads.
 * - **Bringing back** one someday task is the individual way out, to today
 *   or to the inbox.
 * - **Decay** itself isn't a job that runs on a timer. A task becomes
 *   eligible the moment it crosses the threshold, and eligibility is a
 *   query re-evaluated whenever the data changes or the day rolls over
 *   (see useAmnesty()). There's no background timer — the same rule as
 *   Part C3's calendar refresh — and nothing to fall behind while the app
 *   is closed.
 *
 * Every planner is pure and returns forward writes plus their exact
 * inverse, like the rest of the app. See docs/phase_C5_amnesty.md.
 */
import { generateItemId } from '../db/id.js'
import type { Write } from '../db/ops.js'
import { useLocalValue } from '../lib/localStore.js'
import { addLocalDays } from '../scheduling/localDay.js'
import { moveToDay, planScheduleChange } from '../scheduling/schedule.js'
import { toTaskSchedule, type WritePlan } from '../today/dayPlan.js'
import type { DayTask } from '../today/proposal.js'

/** Decision 4's default: untouched for 30 days. */
export const DEFAULT_THRESHOLD_DAYS = 30
export const MIN_THRESHOLD_DAYS = 7
export const MAX_THRESHOLD_DAYS = 365

/** The plan's "undoable for 24 hours." */
export const UNDO_WINDOW_MS = 24 * 60 * 60 * 1000

export const THRESHOLD_KEY = 'life-helper-amnesty-threshold-days'

export function parseThresholdDays(value: unknown): number {
  return typeof value === 'number' &&
    Number.isInteger(value) &&
    value >= MIN_THRESHOLD_DAYS &&
    value <= MAX_THRESHOLD_DAYS
    ? value
    : DEFAULT_THRESHOLD_DAYS
}

/** The threshold, per device — like the other settings on the Settings page. */
export function useThresholdDays(): [number, (days: number) => void] {
  const [days, set] = useLocalValue(THRESHOLD_KEY, parseThresholdDays)
  return [days, set]
}

/**
 * The instant a task must have been last touched before to be eligible:
 * the start of the day `days` days before today. Day-granular, so the
 * eligible set (and the count a confirmation shows) doesn't shift from
 * minute to minute while the sheet is open.
 */
export function untouchedBefore(todayStart: number, days: number): number {
  return addLocalDays(todayStart, -days)
}

/** One row of AMNESTY_ELIGIBLE_SQL. */
export interface EligibleTask {
  readonly id: string
  readonly title: string
  readonly status: string | null
}

/** One row of LATEST_SWEEP_SQL. */
export interface SweepRow {
  readonly id: string
  readonly swept_at: number
  readonly threshold_days: number
  readonly item_count: number
  readonly undone_at: number | null
}

export interface SweepPlan extends WritePlan {
  readonly sweepId: string
}

function taskFieldsWrite(id: string, fields: Write['fields']): Write {
  return { table: 'task_fields', key: { item_id: id }, fields }
}

/**
 * Moves exactly `tasks` — the rows the confirmation counted — to someday,
 * tagged with a new sweep. Only `someday` and `amnesty_sweep_id` change:
 * dates, status, and everything else stay as they were, so bringing a task
 * back (or undoing) finds it exactly where it was.
 */
export function planSweep(args: {
  readonly tasks: readonly EligibleTask[]
  readonly thresholdDays: number
  readonly now?: number
  readonly generateId?: () => string
}): SweepPlan {
  const { tasks, thresholdDays, now = Date.now(), generateId = generateItemId } = args
  if (tasks.length === 0) throw new Error('planSweep(): nothing to sweep')
  const sweepId = generateId()
  const ids = tasks.map((task) => task.id)
  return {
    sweepId,
    writes: [
      {
        table: 'amnesty_sweeps',
        key: { id: sweepId },
        fields: { swept_at: now, threshold_days: thresholdDays, item_count: tasks.length },
      },
      ...ids.map((id) => taskFieldsWrite(id, { someday: 1, amnesty_sweep_id: sweepId })),
    ],
    undoWrites: planUndoSweep({ sweepId, itemIds: ids, now }).writes,
  }
}

/**
 * Undoes a sweep: every task it moved that's still in someday (see
 * SWEPT_ITEMS_SQL) goes back to exactly its prior state — not someday, not
 * tagged — and the sweep is marked undone so its undo isn't offered again.
 */
export function planUndoSweep(args: {
  readonly sweepId: string
  readonly itemIds: readonly string[]
  readonly now?: number
}): { readonly writes: readonly Write[] } {
  const { sweepId, itemIds, now = Date.now() } = args
  return {
    writes: [
      ...itemIds.map((id) => taskFieldsWrite(id, { someday: 0, amnesty_sweep_id: null })),
      { table: 'amnesty_sweeps', key: { id: sweepId }, fields: { undone_at: now } },
    ],
  }
}

/** A sweep's undo is offered until 24 hours after it, unless it's been undone. */
export function canUndoSweep(sweep: SweepRow | undefined, now: number): sweep is SweepRow {
  return sweep !== undefined && sweep.undone_at === null && now - sweep.swept_at < UNDO_WINDOW_MS
}

export function undoDeadline(sweep: SweepRow): number {
  return sweep.swept_at + UNDO_WINDOW_MS
}

/** One row of SOMEDAY_SQL. */
export interface SomedayTask extends DayTask {
  readonly updated_at: number
  readonly amnesty_sweep_id: string | null
}

export type BringBackTo = 'today' | 'inbox'

/**
 * Takes one task out of someday — the plan's "pulled back individually."
 *
 * - **Today**: scheduled for today (keeping its time of day, through C1's
 *   planScheduleChange(), so a move from an earlier day counts like any
 *   other) and active.
 * - **Inbox**: back to be triaged; its dates are left as they were.
 *
 * Either way it's untagged from its sweep (so undoing that sweep later
 * leaves it alone) and `updated_at` is stamped: bringing a task back is
 * working on it, so its decay clock starts again rather than making it
 * eligible for the next sweep straight away.
 */
export function planBringBack(
  task: SomedayTask,
  to: BringBackTo,
  dayStart: number,
  now: number = Date.now(),
): WritePlan {
  const itemsKey = { id: task.id }
  const writes: Write[] = [
    {
      table: 'items',
      key: itemsKey,
      fields: { status: to === 'today' ? 'active' : 'inbox', updated_at: now },
    },
    taskFieldsWrite(task.id, { someday: 0, amnesty_sweep_id: null }),
  ]
  const undoWrites: Write[] = [
    { table: 'items', key: itemsKey, fields: { status: task.status, updated_at: task.updated_at } },
    taskFieldsWrite(task.id, { someday: 1, amnesty_sweep_id: task.amnesty_sweep_id }),
  ]
  if (to === 'today') {
    const schedule = planScheduleChange(
      toTaskSchedule(task),
      { scheduledFor: moveToDay(task.scheduled_for, dayStart) },
      now,
    )
    writes.push(...schedule.writes)
    undoWrites.push(...schedule.undoWrites)
  }
  return { writes, undoWrites }
}

/**
 * Turns what someone typed into a safe FTS5 query: each word becomes a
 * quoted prefix term (`"sour"*`), all of which must match. Quotes are
 * stripped first, so nothing typed can be read as FTS5 syntax. Empty input
 * gives '', which SOMEDAY_SQL reads as "no filter."
 */
export function toFtsQuery(text: string): string {
  return text
    .split(/\s+/)
    .map((word) => word.replace(/"/g, ''))
    .filter((word) => word.length > 0)
    .map((word) => `"${word}"*`)
    .join(' ')
}
