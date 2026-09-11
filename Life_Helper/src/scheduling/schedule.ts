/**
 * Part C1's task scheduling model: three date concepts on `task_fields`
 * that are never conflated.
 *
 * - `due_at` — a real external deadline. Moving it is someone else's
 *   decision, so it never counts against the task.
 * - `scheduled_for` — the day you intend to do it. Freely movable, but
 *   moving it to a later day is a choice, and Decision 4 counts every such
 *   choice: `touch_count` + 1, `last_touched_at` = now.
 * - `defer_until` — the task is hidden from every view before this date.
 *   Deferring is literally a deferral, so pushing the reappearance day
 *   later counts the same way (Decision 4: "incremented on every deferral
 *   or reschedule").
 *
 * `planScheduleChange()` is the single place those rules live. Like
 * Part B3's `planTriageAction()`, it's pure and returns a forward `Write`
 * plus its exact inverse, so a caller's undo is "mutate() the undo writes"
 * — including putting `touch_count` back. Every code path that moves any
 * of the three dates should go through it; triage already does.
 *
 * See docs/phase_C1_scheduling_model.md for why each rule is shaped the
 * way it is.
 */
import type { SqlValue, Write } from '../db/ops.js'
import {
  atLocalTimeOf,
  compareLocalDays,
  startOfLocalDay,
  startOfNextLocalDay,
} from './localDay.js'

/** A task's current scheduling state — a snapshot of its `task_fields` row. */
export interface TaskSchedule {
  readonly id: string
  readonly dueAt: number | null
  readonly scheduledFor: number | null
  readonly deferUntil: number | null
  readonly touchCount: number
  readonly lastTouchedAt: number | null
}

/**
 * Each date is independently settable. A key that's absent (or
 * `undefined`) leaves that date alone; `null` clears it.
 */
export interface ScheduleChange {
  readonly dueAt?: number | null
  readonly scheduledFor?: number | null
  readonly deferUntil?: number | null
}

export interface SchedulePlan {
  /** Zero or one `task_fields` write — empty when nothing would change. */
  readonly writes: readonly Write[]
  /** Restores every field `writes` changes, including `touch_count`/`last_touched_at`. */
  readonly undoWrites: readonly Write[]
  /** Whether this change counted as a reschedule/deferral (touch_count + 1). */
  readonly touched: boolean
}

function assertDate(name: string, value: number | null): void {
  if (value !== null && !Number.isFinite(value)) {
    throw new Error(`planScheduleChange(): ${name} must be a finite epoch-ms number or null`)
  }
}

/**
 * A later local calendar day, or a date cleared entirely. Setting a first
 * date (null → day) is planning, not rescheduling. Moving within the same
 * day (3pm → 6pm) or to an earlier day (pulling work in) isn't a deferral.
 * Clearing a date counts because "clear it, then set it again next week"
 * would otherwise be two uncounted moves that add up to one counted one.
 */
export function isForwardReschedule(previous: number | null, next: number | null): boolean {
  if (previous === null) return false
  if (next === null) return true
  return compareLocalDays(next, previous) > 0
}

/**
 * The `scheduled_for` a task gets when it's moved to `day` by an action
 * that picks only a day — triage's Today key and date picker, committing
 * it to a day's top 3. Keeps the time of day it already had (an item
 * captured as "acne cream 6pm" stays at 6pm) rather than flattening it to
 * midnight; a task with no date yet takes `day` as given.
 */
export function moveToDay(scheduledFor: number | null, day: number): number {
  return scheduledFor === null ? day : atLocalTimeOf(day, scheduledFor)
}

/**
 * The first instant at which a task deferred to any date on or before
 * `now`'s local day is visible again. `defer_until` is a date, not a time:
 * a task deferred to Friday is visible from Friday's first instant,
 * whatever time of day the stored value carries.
 */
export function deferralCutoff(now: number): number {
  return startOfNextLocalDay(now)
}

/** Hidden from every view: `defer_until` is a later local day than `now`'s. */
export function isDeferred(deferUntil: number | null, now: number): boolean {
  return deferUntil !== null && deferUntil >= deferralCutoff(now)
}

/**
 * Pushes the day a hidden task reappears later: either it wasn't hidden
 * and now is, or it was and now reappears on a later day. Un-deferring,
 * or pulling the date in, isn't a deferral. A `defer_until` already in the
 * past is treated as not hidden — re-deferring such a task is a fresh
 * deferral, not a move from a stale date.
 */
function isFurtherDeferral(previous: number | null, next: number | null, now: number): boolean {
  if (next === null || !isDeferred(next, now)) return false
  if (previous === null || !isDeferred(previous, now)) return true
  return compareLocalDays(next, previous) > 0
}

/**
 * Plans a change to any of a task's three dates. At most one
 * `touch_count` increment per call, however many of the dates move —
 * "once per move," where a move is one user action.
 */
export function planScheduleChange(
  task: TaskSchedule,
  change: ScheduleChange,
  now: number,
): SchedulePlan {
  const nextDueAt = change.dueAt === undefined ? task.dueAt : change.dueAt
  const nextScheduledFor =
    change.scheduledFor === undefined ? task.scheduledFor : change.scheduledFor
  let nextDeferUntil = change.deferUntil === undefined ? task.deferUntil : change.deferUntil

  assertDate('dueAt', nextDueAt)
  assertDate('scheduledFor', nextScheduledFor)
  assertDate('deferUntil', nextDeferUntil)

  // Normalized to the day's first instant so every stored defer_until is a
  // date — comparisons and the SQL filter never depend on whatever time of
  // day a caller happened to pass.
  if (change.deferUntil != null) nextDeferUntil = startOfLocalDay(change.deferUntil)

  const fields: Record<string, SqlValue> = {}
  const undoFields: Record<string, SqlValue> = {}

  if (nextDueAt !== task.dueAt) {
    fields.due_at = nextDueAt
    undoFields.due_at = task.dueAt
  }
  if (nextScheduledFor !== task.scheduledFor) {
    fields.scheduled_for = nextScheduledFor
    undoFields.scheduled_for = task.scheduledFor
  }
  if (nextDeferUntil !== task.deferUntil) {
    fields.defer_until = nextDeferUntil
    undoFields.defer_until = task.deferUntil
  }

  // due_at deliberately plays no part here: a deadline change is external,
  // a reschedule is a choice.
  const touched =
    isForwardReschedule(task.scheduledFor, nextScheduledFor) ||
    isFurtherDeferral(task.deferUntil, nextDeferUntil, now)

  if (touched) {
    fields.touch_count = task.touchCount + 1
    fields.last_touched_at = now
    undoFields.touch_count = task.touchCount
    undoFields.last_touched_at = task.lastTouchedAt
  }

  if (Object.keys(fields).length === 0) {
    return { writes: [], undoWrites: [], touched: false }
  }

  const key = { item_id: task.id }
  return {
    writes: [{ table: 'task_fields', key, fields }],
    undoWrites: [{ table: 'task_fields', key, fields: undoFields }],
    touched,
  }
}

/**
 * The deferral filter every task view's SQL must include (Part C1: "deferred
 * items are absent from every view until their date"), bound to
 * `deferralCutoff(now)` — see useDeferralCutoff(). Assumes `task_fields` is
 * joined under its own name; a task with no `task_fields` row at all has a
 * NULL `defer_until` and is visible. schedule.test.ts's source scan fails if
 * a task query anywhere under src/ leaves it out.
 */
export const NOT_DEFERRED_SQL = '(task_fields.defer_until IS NULL OR task_fields.defer_until < ?)'
