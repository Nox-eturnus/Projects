/**
 * Part C4's three actions on a slipping task — do it now, break it down,
 * let it go. Pure, with the same contract as planTriageAction() and
 * planCommitTop3(): each returns forward writes plus their exact inverse,
 * so the undo toast is just "mutate() the undo writes."
 *
 * See docs/phase_C4_slipping.md for why each one is shaped the way it is.
 */
import { generateItemId } from '../db/id.js'
import type { SqlValue, Write } from '../db/ops.js'
import { addLocalDays } from '../scheduling/localDay.js'
import { moveToDay, planScheduleChange } from '../scheduling/schedule.js'
import {
  planCommitTop3,
  toTaskSchedule,
  type DayPlanRow,
  type WritePlan,
} from '../today/dayPlan.js'
import type { DayTask } from '../today/proposal.js'

/** One row of SLIPPING_SQL. */
export interface SlippingTask extends DayTask {
  /** The project it's filed under, if any — copied onto the steps it's broken into. */
  readonly project_id: string | null
}

function itemsWrite(id: string, fields: Readonly<Record<string, SqlValue>>): Write {
  return { table: 'items', key: { id }, fields }
}

// --- Do it now -------------------------------------------------------------

/**
 * Pulls `task` into today's top 3. `slots` is today's committed three as
 * Today shows them (committed ids that still resolve to a task, in slot
 * order). With a free slot it's appended; with three, `replace` names the
 * slot's task it takes the place of — the replaced task stays scheduled
 * for today, it just isn't one of the three any more.
 *
 * Goes through planCommitTop3(), so the task is moved to today exactly the
 * way any commitment moves it (C1's rules: a task from an earlier day
 * moving to today is a reschedule, and counts). A day with no plan yet is
 * committed `via: 'proposal'` — the only other value `day_plans` allows
 * is 'shutdown' — and an existing plan keeps how it was committed.
 */
export function planDoItNow(args: {
  readonly task: DayTask
  readonly dayStart: number
  readonly slots: readonly DayTask[]
  readonly existing: DayPlanRow | undefined
  readonly replace?: string
  readonly now?: number
}): WritePlan {
  const { task, dayStart, slots, existing, replace, now = Date.now() } = args
  if (slots.some((slot) => slot.id === task.id)) {
    throw new Error('planDoItNow(): the task is already one of the three')
  }
  let tasks: DayTask[]
  if (slots.length < 3) {
    tasks = [...slots, task]
  } else {
    if (replace === undefined || !slots.some((slot) => slot.id === replace)) {
      throw new Error('planDoItNow(): the three are full; name the slot to replace')
    }
    tasks = slots.map((slot) => (slot.id === replace ? task : slot))
  }
  return planCommitTop3({
    dayStart,
    tasks,
    via: existing?.committed_via ?? 'proposal',
    existing,
    now,
  })
}

/**
 * When all of today's three are already done there's no slot worth
 * replacing, so "do it now" puts the task on today without touching the
 * three: scheduled for today (keeping its time of day), out of the inbox.
 */
export function planScheduleForToday(
  task: DayTask,
  dayStart: number,
  now: number = Date.now(),
): WritePlan {
  const schedule = planScheduleChange(
    toTaskSchedule(task),
    { scheduledFor: moveToDay(task.scheduled_for, dayStart) },
    now,
  )
  return {
    writes: [itemsWrite(task.id, { status: 'active' }), ...schedule.writes],
    undoWrites: [itemsWrite(task.id, { status: task.status }), ...schedule.undoWrites],
  }
}

// --- Break it down ---------------------------------------------------------

/** When the new steps land: today, tomorrow, or the inbox to be triaged later. */
export type StepsWhen = 'today' | 'tomorrow' | 'inbox'

/** Most steps one break-down creates: a plan this long is a project, not a task. */
export const MAX_STEPS = 8

export interface BreakDownPlan extends WritePlan {
  readonly stepIds: readonly string[]
}

/**
 * Replaces `parent` with smaller steps: one new task per non-blank title,
 * each linked to the parent (`rel: 'subtask_of'`, step → parent), filed
 * under the parent's project if it had one, and carrying the parent's
 * deadline (a real deadline applies to every piece of the work). The
 * parent is archived — `status: 'archived'` — so it's kept, and its steps
 * can point at it, but it's out of every list.
 *
 * Steps are fresh tasks, so they start with `touch_count` 0: breaking a
 * task down is a decision, and the pieces get a clean slate. Undo
 * tombstones the steps and their links (Decision 2: never `DELETE FROM`)
 * and un-archives the parent.
 */
export function planBreakDown(args: {
  readonly parent: SlippingTask
  readonly steps: readonly string[]
  readonly when: StepsWhen
  readonly dayStart: number
  readonly now?: number
  readonly generateId?: () => string
}): BreakDownPlan {
  const { parent, when, dayStart, now = Date.now(), generateId = generateItemId } = args
  const titles = args.steps.map((step) => step.trim()).filter((step) => step.length > 0)
  if (titles.length === 0) throw new Error('planBreakDown(): at least one step is needed')
  if (titles.length > MAX_STEPS) {
    throw new Error(`planBreakDown(): at most ${String(MAX_STEPS)} steps`)
  }

  const scheduledFor =
    when === 'today' ? dayStart : when === 'tomorrow' ? addLocalDays(dayStart, 1) : null
  const writes: Write[] = []
  const undoWrites: Write[] = []
  const stepIds: string[] = []

  titles.forEach((title, index) => {
    const id = generateId()
    stepIds.push(id)
    // One millisecond apart, so the steps keep their order wherever a list
    // sorts by creation time.
    const createdAt = now + index
    writes.push(
      itemsWrite(id, {
        kind: 'task',
        title,
        status: when === 'inbox' ? 'inbox' : 'active',
        created_at: createdAt,
        updated_at: createdAt,
      }),
      {
        table: 'task_fields',
        key: { item_id: id },
        fields: {
          ...(scheduledFor === null ? {} : { scheduled_for: scheduledFor }),
          ...(parent.due_at === null ? {} : { due_at: parent.due_at }),
        },
      },
      {
        table: 'links',
        key: { from_id: id, to_id: parent.id, rel: 'subtask_of' },
        fields: { created_at: now },
      },
    )
    undoWrites.push(itemsWrite(id, { deleted_at: now }), {
      table: 'links',
      key: { from_id: id, to_id: parent.id, rel: 'subtask_of' },
      fields: { deleted_at: now },
    })
    if (parent.project_id !== null) {
      const key = { from_id: id, to_id: parent.project_id, rel: 'project' }
      writes.push({ table: 'links', key, fields: { created_at: now } })
      undoWrites.push({ table: 'links', key, fields: { deleted_at: now } })
    }
  })

  writes.push(itemsWrite(parent.id, { status: 'archived' }))
  undoWrites.push(itemsWrite(parent.id, { status: parent.status }))

  return { writes, undoWrites, stepIds }
}

// --- Let it go ---------------------------------------------------------------

export type LetGoChoice = 'someday' | 'delete'

/**
 * The plan's "kill it": someday (Decision 4's tier — out of Today, Revisit,
 * and every count, kept and searchable) or delete (a tombstone, like every
 * delete in this app).
 */
export function planLetGo(task: DayTask, choice: LetGoChoice, now: number = Date.now()): WritePlan {
  if (choice === 'someday') {
    const key = { item_id: task.id }
    return {
      writes: [{ table: 'task_fields', key, fields: { someday: 1 } }],
      undoWrites: [{ table: 'task_fields', key, fields: { someday: 0 } }],
    }
  }
  return {
    writes: [itemsWrite(task.id, { deleted_at: now })],
    undoWrites: [itemsWrite(task.id, { deleted_at: null })],
  }
}
