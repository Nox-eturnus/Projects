// @vitest-environment node
import { DatabaseSync } from 'node:sqlite'
import { describe, expect, it } from 'vitest'
import { createHlcClock, type HlcState } from '../db/hlc'
import { applyMigrations, type SqliteConnection } from '../db/migrate'
import { compareMaterializedTables, mutate, replayOps, selectAllOps, type Write } from '../db/ops'
import { DAY_PLANS_SQL, DAY_TASKS_SQL, SLIPPING_SQL } from '../routes/taskQueries'
import { addLocalDays, localDayKey, startOfLocalDay } from '../scheduling/localDay'
import { deferralCutoff } from '../scheduling/schedule'
import { committedIds, type DayPlanRow } from '../today/dayPlan'
import { findSlipping } from './slipping'
import {
  MAX_STEPS,
  planBreakDown,
  planDoItNow,
  planLetGo,
  planScheduleForToday,
  type SlippingTask,
} from './slippingActions'

const HOUR_MS = 60 * 60 * 1000
const TODAY = startOfLocalDay(Date.UTC(2026, 9, 2, 12))
const YESTERDAY = addLocalDays(TODAY, -1)
const TOMORROW = addLocalDays(TODAY, 1)
const NOW = TODAY + 10 * HOUR_MS

function task(id: string, overrides: Partial<SlippingTask> = {}): SlippingTask {
  return {
    id,
    title: id,
    status: 'active',
    created_at: 1_000,
    due_at: null,
    scheduled_for: null,
    defer_until: null,
    touch_count: 0,
    last_touched_at: null,
    completed_at: null,
    estimate_min: null,
    project_id: null,
    ...overrides,
  }
}

function dayPlanWrite(plan: { writes: readonly Write[] }): Write | undefined {
  return plan.writes.find((write) => write.table === 'day_plans')
}

describe('do it now', () => {
  it('with a free slot, appends the task to today’s three', () => {
    const slots = [task('a', { scheduled_for: TODAY })]
    const plan = planDoItNow({
      task: task('slipping', { touch_count: 2 }),
      dayStart: TODAY,
      slots,
      existing: undefined,
      now: NOW,
    })
    expect(dayPlanWrite(plan)?.fields).toMatchObject({
      top1_id: 'a',
      top2_id: 'slipping',
      top3_id: null,
      committed_via: 'proposal',
    })
  })

  it('with three, replaces the named slot in place and keeps the others’ order', () => {
    const slots = ['a', 'b', 'c'].map((id) => task(id, { scheduled_for: TODAY }))
    const existing = { committed_via: 'shutdown' } as DayPlanRow
    const plan = planDoItNow({
      task: task('slipping', { touch_count: 1 }),
      dayStart: TODAY,
      slots,
      existing,
      replace: 'b',
      now: NOW,
    })
    expect(dayPlanWrite(plan)?.fields).toMatchObject({
      top1_id: 'a',
      top2_id: 'slipping',
      top3_id: 'c',
      // An existing plan keeps how it was committed.
      committed_via: 'shutdown',
    })
  })

  it('refuses to guess: three full slots need a slot to replace', () => {
    const slots = ['a', 'b', 'c'].map((id) => task(id))
    expect(() =>
      planDoItNow({ task: task('x'), dayStart: TODAY, slots, existing: undefined }),
    ).toThrow(/name the slot/)
    expect(() =>
      planDoItNow({ task: task('x'), dayStart: TODAY, slots, existing: undefined, replace: 'zz' }),
    ).toThrow(/name the slot/)
  })

  it('moves a task from an earlier day to today — a reschedule, counted once (C1)', () => {
    const plan = planDoItNow({
      task: task('from-yesterday', { scheduled_for: YESTERDAY + 18 * HOUR_MS, touch_count: 1 }),
      dayStart: TODAY,
      slots: [],
      existing: undefined,
      now: NOW,
    })
    const fields = plan.writes.find((write) => write.table === 'task_fields')?.fields
    // Keeps its 6pm.
    expect(fields).toMatchObject({ scheduled_for: TODAY + 18 * HOUR_MS, touch_count: 2 })
  })

  it('when all three are done, puts it on today without touching the three', () => {
    const plan = planScheduleForToday(
      task('x', { status: 'inbox', scheduled_for: YESTERDAY }),
      TODAY,
      NOW,
    )
    expect(plan.writes.some((write) => write.table === 'day_plans')).toBe(false)
    expect(plan.writes).toContainEqual({
      table: 'items',
      key: { id: 'x' },
      fields: { status: 'active' },
    })
    expect(plan.undoWrites).toContainEqual({
      table: 'items',
      key: { id: 'x' },
      fields: { status: 'inbox' },
    })
  })
})

describe('break it down', () => {
  function ids() {
    let n = 0
    return () => `step-${String(++n)}`
  }

  it('one active task per non-blank step, linked to the parent, which is archived', () => {
    const plan = planBreakDown({
      parent: task('big', { status: 'active' }),
      steps: ['Outline', '   ', 'Draft intro'],
      when: 'today',
      dayStart: TODAY,
      now: NOW,
      generateId: ids(),
    })
    expect(plan.stepIds).toEqual(['step-1', 'step-2'])
    expect(plan.writes).toContainEqual({
      table: 'items',
      key: { id: 'step-1' },
      fields: {
        kind: 'task',
        title: 'Outline',
        status: 'active',
        created_at: NOW,
        updated_at: NOW,
      },
    })
    expect(plan.writes).toContainEqual({
      table: 'task_fields',
      key: { item_id: 'step-2' },
      fields: { scheduled_for: TODAY },
    })
    expect(plan.writes).toContainEqual({
      table: 'links',
      key: { from_id: 'step-2', to_id: 'big', rel: 'subtask_of' },
      fields: { created_at: NOW },
    })
    expect(plan.writes.at(-1)).toEqual({
      table: 'items',
      key: { id: 'big' },
      fields: { status: 'archived' },
    })
  })

  it('steps keep their order by creation time', () => {
    const plan = planBreakDown({
      parent: task('big'),
      steps: ['one', 'two', 'three'],
      when: 'today',
      dayStart: TODAY,
      now: NOW,
      generateId: ids(),
    })
    const created = plan.writes
      .filter((write) => write.table === 'items' && 'created_at' in write.fields)
      .map((write) => write.fields.created_at)
    expect(created).toEqual([NOW, NOW + 1, NOW + 2])
  })

  it('tomorrow, or the inbox with no date — and the deadline and project come along', () => {
    const parent = task('big', { due_at: TOMORROW + 17 * HOUR_MS, project_id: 'proj-1' })
    const tomorrow = planBreakDown({
      parent,
      steps: ['a'],
      when: 'tomorrow',
      dayStart: TODAY,
      now: NOW,
      generateId: ids(),
    })
    expect(tomorrow.writes).toContainEqual({
      table: 'task_fields',
      key: { item_id: 'step-1' },
      fields: { scheduled_for: TOMORROW, due_at: TOMORROW + 17 * HOUR_MS },
    })
    expect(tomorrow.writes).toContainEqual({
      table: 'links',
      key: { from_id: 'step-1', to_id: 'proj-1', rel: 'project' },
      fields: { created_at: NOW },
    })

    const inbox = planBreakDown({
      parent,
      steps: ['a'],
      when: 'inbox',
      dayStart: TODAY,
      now: NOW,
      generateId: ids(),
    })
    expect(inbox.writes).toContainEqual({
      table: 'task_fields',
      key: { item_id: 'step-1' },
      fields: { due_at: TOMORROW + 17 * HOUR_MS },
    })
    expect(inbox.writes[0].fields).toMatchObject({ status: 'inbox' })
  })

  it('needs at least one step, and at most MAX_STEPS', () => {
    const base = { parent: task('big'), when: 'today' as const, dayStart: TODAY }
    expect(() => planBreakDown({ ...base, steps: ['', '  '] })).toThrow(/at least one/)
    expect(() =>
      planBreakDown({ ...base, steps: Array.from({ length: MAX_STEPS + 1 }, () => 'x') }),
    ).toThrow(/at most/)
  })
})

describe('let it go', () => {
  it('someday, and its undo', () => {
    const plan = planLetGo(task('x'), 'someday', NOW)
    expect(plan.writes).toEqual([
      { table: 'task_fields', key: { item_id: 'x' }, fields: { someday: 1 } },
    ])
    expect(plan.undoWrites).toEqual([
      { table: 'task_fields', key: { item_id: 'x' }, fields: { someday: 0 } },
    ])
  })

  it('delete is a tombstone, and its undo lifts it', () => {
    const plan = planLetGo(task('x'), 'delete', NOW)
    expect(plan.writes).toEqual([{ table: 'items', key: { id: 'x' }, fields: { deleted_at: NOW } }])
    expect(plan.undoWrites).toEqual([
      { table: 'items', key: { id: 'x' }, fields: { deleted_at: null } },
    ])
  })
})

// --- Against a real database, through the real write path ------------------

function memoryStore() {
  let state: HlcState | undefined
  return {
    load: () => state,
    save: (next: HlcState) => {
      state = next
    },
  }
}

function freshDb(): SqliteConnection {
  const db = new DatabaseSync(':memory:')
  applyMigrations(db)
  return db
}

type Clock = ReturnType<typeof createHlcClock>

function addTask(
  db: SqliteConnection,
  clock: Clock,
  id: string,
  fields: Record<string, number | null>,
  status = 'active',
) {
  mutate(
    db,
    {
      writes: [
        {
          table: 'items',
          key: { id },
          fields: { kind: 'task', title: id, status, created_at: 1, updated_at: 1 },
        },
        { table: 'task_fields', key: { item_id: id }, fields },
      ],
    },
    'device-1',
    clock,
  )
}

function slippingRows(db: SqliteConnection): SlippingTask[] {
  return db.prepare(SLIPPING_SQL).all(deferralCutoff(TODAY), TODAY) as unknown as SlippingTask[]
}

function slippingIds(db: SqliteConnection): string[] {
  return findSlipping(slippingRows(db), TODAY).map((row) => row.id)
}

function dayTaskIds(db: SqliteConnection): string[] {
  return (db.prepare(DAY_TASKS_SQL).all(deferralCutoff(TODAY), TODAY) as { id: string }[])
    .map((row) => row.id)
    .sort()
}

function expectReplayMatches(db: SqliteConnection) {
  const replayed = freshDb()
  replayOps(replayed, selectAllOps(db))
  expect(compareMaterializedTables(db, replayed).ok).toBe(true)
}

function seed() {
  const db = freshDb()
  const clock = createHlcClock('device-1', memoryStore())
  addTask(db, clock, 'moved-thrice', { touch_count: 3, last_touched_at: YESTERDAY })
  addTask(db, clock, 'from-yesterday', { scheduled_for: YESTERDAY })
  addTask(db, clock, 'today-fresh', { scheduled_for: TODAY })
  addTask(db, clock, 'someday', { touch_count: 4, someday: 1 })
  addTask(db, clock, 'deferred', { touch_count: 4, defer_until: TOMORROW })
  addTask(db, clock, 'archived', { touch_count: 5 }, 'archived')
  return { db, clock }
}

describe('on a real database', () => {
  it('SLIPPING_SQL + findSlipping: never someday, deferred, or archived; ranked', () => {
    const { db } = seed()
    expect(slippingIds(db)).toEqual(['moved-thrice', 'from-yesterday'])
  })

  it('archived tasks are gone from Today’s query too', () => {
    const { db } = seed()
    expect(dayTaskIds(db)).not.toContain('archived')
  })

  it('SLIPPING_SQL carries the project a task is filed under', () => {
    const { db, clock } = seed()
    mutate(
      db,
      {
        writes: [
          {
            table: 'links',
            key: { from_id: 'moved-thrice', to_id: 'proj-1', rel: 'project' },
            fields: { created_at: 5 },
          },
        ],
      },
      'device-1',
      clock,
    )
    const rows = slippingRows(db)
    expect(rows.find((row) => row.id === 'moved-thrice')?.project_id).toBe('proj-1')
    expect(rows.find((row) => row.id === 'from-yesterday')?.project_id).toBeNull()
  })

  it('do it now: committed for today, gone from the slipping list; undo restores both', () => {
    const { db, clock } = seed()
    const target = slippingRows(db).find((row) => row.id === 'from-yesterday') as SlippingTask
    const plan = planDoItNow({
      task: target,
      dayStart: TODAY,
      slots: [],
      existing: undefined,
      now: NOW,
    })
    mutate(db, { writes: plan.writes }, 'device-1', clock)

    const key = localDayKey(TODAY)
    const committed = committedIds(
      (db.prepare(DAY_PLANS_SQL).all(key, key) as unknown as DayPlanRow[])[0],
    )
    expect(committed).toEqual(['from-yesterday'])
    expect(findSlipping(slippingRows(db), TODAY, new Set(committed)).map((r) => r.id)).toEqual([
      'moved-thrice',
    ])

    mutate(db, { writes: plan.undoWrites }, 'device-1', clock)
    expect(
      committedIds((db.prepare(DAY_PLANS_SQL).all(key, key) as unknown as DayPlanRow[])[0]),
    ).toEqual([])
    expect(slippingIds(db)).toEqual(['moved-thrice', 'from-yesterday'])
    const row = slippingRows(db).find((r) => r.id === 'from-yesterday')
    expect(row).toMatchObject({ scheduled_for: YESTERDAY, touch_count: 0 })
    expectReplayMatches(db)
  })

  it('break it down: steps appear on today, the parent leaves every list; undo puts it all back', () => {
    const { db, clock } = seed()
    const parent = slippingRows(db).find((row) => row.id === 'moved-thrice') as SlippingTask
    let n = 0
    const plan = planBreakDown({
      parent,
      steps: ['First step', 'Second step'],
      when: 'today',
      dayStart: TODAY,
      now: NOW,
      generateId: () => `step-${String(++n)}`,
    })
    mutate(db, { writes: plan.writes }, 'device-1', clock)

    expect(dayTaskIds(db)).toEqual(['from-yesterday', 'step-1', 'step-2', 'today-fresh'])
    expect(slippingIds(db)).toEqual(['from-yesterday'])
    const links = db
      .prepare(
        `SELECT from_id FROM links WHERE to_id = ? AND rel = 'subtask_of' AND deleted_at IS NULL`,
      )
      .all('moved-thrice')
      .map((row) => row.from_id)
    expect(links).toEqual(['step-1', 'step-2'])

    mutate(db, { writes: plan.undoWrites }, 'device-1', clock)
    expect(dayTaskIds(db)).toEqual(['from-yesterday', 'moved-thrice', 'today-fresh'])
    expect(slippingIds(db)).toEqual(['moved-thrice', 'from-yesterday'])
    const liveLinks = db
      .prepare(`SELECT from_id FROM links WHERE rel = 'subtask_of' AND deleted_at IS NULL`)
      .all()
    expect(liveLinks).toEqual([])
    expectReplayMatches(db)
  })

  it('let it go: someday and delete each leave the list, and each undo brings it back', () => {
    for (const choice of ['someday', 'delete'] as const) {
      const { db, clock } = seed()
      const target = slippingRows(db).find((row) => row.id === 'moved-thrice') as SlippingTask
      const plan = planLetGo(target, choice, NOW)
      mutate(db, { writes: plan.writes }, 'device-1', clock)
      expect(slippingIds(db)).toEqual(['from-yesterday'])
      mutate(db, { writes: plan.undoWrites }, 'device-1', clock)
      expect(slippingIds(db)).toEqual(['moved-thrice', 'from-yesterday'])
      expectReplayMatches(db)
    }
  })
})
