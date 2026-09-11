/**
 * Part C2's writes: committing a day's top 3, completing the evening
 * shutdown, and ticking a task off from Today. Pure — each returns the
 * forward writes plus their exact inverse, the same contract as
 * planTriageAction() and planScheduleChange(), so every action here can be
 * undone by mutate()-ing its undo writes.
 *
 * A day's plan lives in `day_plans`, keyed by the local date
 * (localDayKey()): three slot columns, when and how they were committed,
 * and — on the evening's own row — when that evening's shutdown finished.
 * See docs/phase_C2_today_shutdown.md for why that's a table of its own.
 *
 * `now` defaults to the moment each function is called, the way parse()
 * does, so route event handlers don't call Date.now() in their own bodies
 * (react-hooks/purity can't tell a click handler from render code). Tests
 * always pass it explicitly.
 */
import type { SqlValue, Write } from '../db/ops.js'
import { localDayKey } from '../scheduling/localDay.js'
import { moveToDay, planScheduleChange, type TaskSchedule } from '../scheduling/schedule.js'
import type { DayTask } from './proposal.js'

export type CommitVia = 'shutdown' | 'proposal'

/** One row of `day_plans`. */
export interface DayPlanRow {
  readonly day: string
  readonly top1_id: string | null
  readonly top2_id: string | null
  readonly top3_id: string | null
  readonly committed_at: number | null
  readonly committed_via: CommitVia | null
  readonly shutdown_completed_at: number | null
}

export interface WritePlan {
  readonly writes: readonly Write[]
  readonly undoWrites: readonly Write[]
}

/** A day's committed top 3, in slot order — empty if nothing was committed. */
export function committedIds(plan: DayPlanRow | undefined): string[] {
  if (!plan || plan.committed_at === null) return []
  return [plan.top1_id, plan.top2_id, plan.top3_id].filter((id): id is string => id !== null)
}

export function toTaskSchedule(task: DayTask): TaskSchedule {
  return {
    id: task.id,
    dueAt: task.due_at,
    scheduledFor: task.scheduled_for,
    deferUntil: task.defer_until,
    touchCount: task.touch_count,
    lastTouchedAt: task.last_touched_at,
  }
}

function itemsWrite(id: string, fields: Readonly<Record<string, SqlValue>>): Write {
  return { table: 'items', key: { id }, fields }
}

/**
 * Commits `tasks` (at most three, in order) as the top 3 for the day
 * starting at `dayStart`, replacing whatever that day had. Committing a
 * task to a day is intending to do it that day — which is exactly what
 * `scheduled_for` means — so each one is also moved to that day through
 * Part C1's planScheduleChange(), keeping its time of day. That's what
 * makes "carry today's unfinished task into tomorrow's three" count as the
 * reschedule it is. Each is also taken out of the inbox: choosing it for a
 * day is a triage decision.
 */
export function planCommitTop3(args: {
  readonly dayStart: number
  readonly tasks: readonly DayTask[]
  readonly via: CommitVia
  readonly existing: DayPlanRow | undefined
  /** Defaults to the moment of the call — see the module comment. */
  readonly now?: number
}): WritePlan {
  const { dayStart, tasks, via, existing, now = Date.now() } = args
  if (tasks.length > 3) {
    throw new Error(`planCommitTop3(): a day has three slots, got ${String(tasks.length)} tasks`)
  }

  const key = { day: localDayKey(dayStart) }
  const writes: Write[] = [
    {
      table: 'day_plans',
      key,
      fields: {
        // .at(), not [i]: this project doesn't set noUncheckedIndexedAccess,
        // so a plain index would type as always-defined.
        top1_id: tasks.at(0)?.id ?? null,
        top2_id: tasks.at(1)?.id ?? null,
        top3_id: tasks.at(2)?.id ?? null,
        committed_at: now,
        committed_via: via,
      },
    },
  ]
  const undoWrites: Write[] = [
    {
      table: 'day_plans',
      key,
      fields: {
        top1_id: existing?.top1_id ?? null,
        top2_id: existing?.top2_id ?? null,
        top3_id: existing?.top3_id ?? null,
        committed_at: existing?.committed_at ?? null,
        committed_via: existing?.committed_via ?? null,
      },
    },
  ]

  for (const task of tasks) {
    const schedule = planScheduleChange(
      toTaskSchedule(task),
      { scheduledFor: moveToDay(task.scheduled_for, dayStart) },
      now,
    )
    writes.push(itemsWrite(task.id, { status: 'active' }), ...schedule.writes)
    undoWrites.push(itemsWrite(task.id, { status: task.status }), ...schedule.undoWrites)
  }

  return { writes, undoWrites }
}

/**
 * The evening shutdown's single commit: tomorrow's top 3 (as
 * planCommitTop3() with `via: 'shutdown'`), plus today's
 * `shutdown_completed_at` — the record Part C6's "shutdown ritual completed
 * on at least 5 of 7 days" is counted from, and what tells Today's
 * reminder that tonight's shutdown is already done.
 */
export function planShutdown(args: {
  readonly todayStart: number
  readonly tomorrowStart: number
  readonly picks: readonly DayTask[]
  readonly existingToday: DayPlanRow | undefined
  readonly existingTomorrow: DayPlanRow | undefined
  /** Defaults to the moment of the call — see the module comment. */
  readonly now?: number
}): WritePlan {
  const now = args.now ?? Date.now()
  const commit = planCommitTop3({
    dayStart: args.tomorrowStart,
    tasks: args.picks,
    via: 'shutdown',
    existing: args.existingTomorrow,
    now,
  })
  const todayKey = { day: localDayKey(args.todayStart) }
  return {
    writes: [
      ...commit.writes,
      { table: 'day_plans', key: todayKey, fields: { shutdown_completed_at: now } },
    ],
    undoWrites: [
      ...commit.undoWrites,
      {
        table: 'day_plans',
        key: todayKey,
        fields: { shutdown_completed_at: args.existingToday?.shutdown_completed_at ?? null },
      },
    ],
  }
}

/**
 * Ticks a task off (or back on). A task completed straight from Today
 * while still in the inbox also leaves the inbox — otherwise it would sit
 * there, done, waiting to be triaged — and un-ticking puts it back.
 */
export function planSetCompleted(
  task: DayTask,
  done: boolean,
  now: number = Date.now(),
): WritePlan {
  const taskKey = { item_id: task.id }
  const writes: Write[] = [
    { table: 'task_fields', key: taskKey, fields: { completed_at: done ? now : null } },
  ]
  const undoWrites: Write[] = [
    { table: 'task_fields', key: taskKey, fields: { completed_at: task.completed_at } },
  ]
  if (done && task.status === 'inbox') {
    writes.push(itemsWrite(task.id, { status: 'active' }))
    undoWrites.push(itemsWrite(task.id, { status: 'inbox' }))
  }
  return { writes, undoWrites }
}
