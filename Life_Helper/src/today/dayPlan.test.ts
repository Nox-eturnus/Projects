/// <reference types="node" />
import { DatabaseSync } from 'node:sqlite'
import { describe, expect, it } from 'vitest'
import { createHlcClock, type HlcState } from '../db/hlc'
import { applyMigrations, type SqliteConnection } from '../db/migrate'
import { compareMaterializedTables, mutate, replayOps, selectAllOps, type Write } from '../db/ops'
import { DAY_PLANS_SQL, DAY_TASKS_SQL, LAST_ACTIVITY_SQL } from '../routes/taskQueries'
import { addLocalDays, localDayKey, startOfLocalDay } from '../scheduling/localDay'
import { deferralCutoff } from '../scheduling/schedule'
import {
  committedIds,
  planCommitTop3,
  planSetCompleted,
  planShutdown,
  type DayPlanRow,
} from './dayPlan'
import type { DayTask } from './proposal'

const HOUR_MS = 60 * 60 * 1000
const NOW = new Date(2026, 8, 11, 21, 0).getTime() // Fri 11 Sep 2026, 21:00
const TODAY = startOfLocalDay(NOW)
const TOMORROW = addLocalDays(TODAY, 1)
const YESTERDAY = addLocalDays(TODAY, -1)

function task(id: string, overrides: Partial<DayTask> = {}): DayTask {
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
    ...overrides,
  }
}

function writeFor(writes: readonly Write[], table: string, id: string): Write | undefined {
  return writes.find((w) => w.table === table && Object.values(w.key).includes(id))
}

describe('committedIds', () => {
  it('lists the filled slots in order, and nothing for an uncommitted plan', () => {
    const plan: DayPlanRow = {
      day: '2026-09-11',
      top1_id: 'a',
      top2_id: null,
      top3_id: 'c',
      committed_at: 1,
      committed_via: 'shutdown',
      shutdown_completed_at: null,
    }
    expect(committedIds(plan)).toEqual(['a', 'c'])
    expect(committedIds({ ...plan, committed_at: null })).toEqual([])
    expect(committedIds(undefined)).toEqual([])
  })
})

describe('planCommitTop3', () => {
  it('writes the three slots into that date’s day_plans row', () => {
    const plan = planCommitTop3({
      dayStart: TODAY,
      tasks: [task('a'), task('b'), task('c')],
      via: 'proposal',
      existing: undefined,
      now: NOW,
    })
    expect(plan.writes[0]).toEqual({
      table: 'day_plans',
      key: { day: '2026-09-11' },
      fields: {
        top1_id: 'a',
        top2_id: 'b',
        top3_id: 'c',
        committed_at: NOW,
        committed_via: 'proposal',
      },
    })
  })

  it('fewer than three leaves the remaining slots empty', () => {
    const plan = planCommitTop3({
      dayStart: TODAY,
      tasks: [task('a')],
      via: 'proposal',
      existing: undefined,
      now: NOW,
    })
    expect(plan.writes[0].fields).toMatchObject({ top1_id: 'a', top2_id: null, top3_id: null })
  })

  it('refuses a fourth task', () => {
    expect(() =>
      planCommitTop3({
        dayStart: TODAY,
        tasks: ['a', 'b', 'c', 'd'].map((id) => task(id)),
        via: 'proposal',
        existing: undefined,
        now: NOW,
      }),
    ).toThrow(/three slots/)
  })

  it('moves each task to that day (keeping its time) and out of the inbox', () => {
    const plan = planCommitTop3({
      dayStart: TODAY,
      tasks: [
        task('unscheduled', { status: 'inbox' }),
        task('next-week-6pm', { scheduled_for: addLocalDays(TODAY, 7) + 18 * HOUR_MS }),
      ],
      via: 'proposal',
      existing: undefined,
      now: NOW,
    })
    expect(writeFor(plan.writes, 'items', 'unscheduled')?.fields).toEqual({ status: 'active' })
    expect(writeFor(plan.writes, 'task_fields', 'unscheduled')?.fields).toEqual({
      scheduled_for: TODAY,
    })
    // Pulled in from next week: planned, not a reschedule.
    expect(writeFor(plan.writes, 'task_fields', 'next-week-6pm')?.fields).toEqual({
      scheduled_for: TODAY + 18 * HOUR_MS,
    })
  })

  it('carrying an unfinished task forward counts as the reschedule it is (Part C1)', () => {
    const plan = planCommitTop3({
      dayStart: TODAY,
      tasks: [task('from-yesterday', { scheduled_for: YESTERDAY + 18 * HOUR_MS, touch_count: 1 })],
      via: 'proposal',
      existing: undefined,
      now: NOW,
    })
    expect(writeFor(plan.writes, 'task_fields', 'from-yesterday')?.fields).toEqual({
      scheduled_for: TODAY + 18 * HOUR_MS,
      touch_count: 2,
      last_touched_at: NOW,
    })
  })

  it('undo restores the previous plan and every task exactly', () => {
    const existing: DayPlanRow = {
      day: '2026-09-11',
      top1_id: 'old',
      top2_id: null,
      top3_id: null,
      committed_at: 5,
      committed_via: 'shutdown',
      shutdown_completed_at: 7,
    }
    const plan = planCommitTop3({
      dayStart: TODAY,
      tasks: [task('a', { status: 'inbox', scheduled_for: YESTERDAY })],
      via: 'proposal',
      existing,
      now: NOW,
    })
    expect(plan.undoWrites).toEqual([
      {
        table: 'day_plans',
        key: { day: '2026-09-11' },
        fields: {
          top1_id: 'old',
          top2_id: null,
          top3_id: null,
          committed_at: 5,
          committed_via: 'shutdown',
        },
      },
      { table: 'items', key: { id: 'a' }, fields: { status: 'inbox' } },
      {
        table: 'task_fields',
        key: { item_id: 'a' },
        fields: { scheduled_for: YESTERDAY, touch_count: 0, last_touched_at: null },
      },
    ])
  })
})

describe('planShutdown', () => {
  it("commits tomorrow's three and stamps tonight's shutdown on today's row", () => {
    const plan = planShutdown({
      todayStart: TODAY,
      tomorrowStart: TOMORROW,
      picks: [task('a')],
      existingToday: undefined,
      existingTomorrow: undefined,
      now: NOW,
    })
    expect(plan.writes[0]).toMatchObject({
      table: 'day_plans',
      key: { day: '2026-09-12' },
      fields: { top1_id: 'a', committed_via: 'shutdown', committed_at: NOW },
    })
    expect(plan.writes.at(-1)).toEqual({
      table: 'day_plans',
      key: { day: '2026-09-11' },
      fields: { shutdown_completed_at: NOW },
    })
  })

  it('finishing with no picks still records the shutdown', () => {
    const plan = planShutdown({
      todayStart: TODAY,
      tomorrowStart: TOMORROW,
      picks: [],
      existingToday: undefined,
      existingTomorrow: undefined,
      now: NOW,
    })
    expect(plan.writes.at(-1)?.fields).toEqual({ shutdown_completed_at: NOW })
  })
})

describe('planSetCompleted', () => {
  it('ticks a task off and un-ticks it', () => {
    expect(planSetCompleted(task('a'), true, NOW).writes).toEqual([
      { table: 'task_fields', key: { item_id: 'a' }, fields: { completed_at: NOW } },
    ])
    expect(planSetCompleted(task('a', { completed_at: 9 }), false, NOW).writes).toEqual([
      { table: 'task_fields', key: { item_id: 'a' }, fields: { completed_at: null } },
    ])
  })

  it('a task ticked off while still in the inbox leaves the inbox; undo puts it back', () => {
    const plan = planSetCompleted(task('a', { status: 'inbox' }), true, NOW)
    expect(plan.writes).toContainEqual({
      table: 'items',
      key: { id: 'a' },
      fields: { status: 'active' },
    })
    expect(plan.undoWrites).toContainEqual({
      table: 'items',
      key: { id: 'a' },
      fields: { status: 'inbox' },
    })
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

function seed(db: SqliteConnection, clock: ReturnType<typeof createHlcClock>) {
  const rows: [string, Record<string, number | null>][] = [
    ['scheduled-today', { scheduled_for: TODAY + 18 * HOUR_MS }],
    ['from-yesterday', { scheduled_for: YESTERDAY }],
    ['due-today', { due_at: TODAY + 17 * HOUR_MS }],
    ['someday', { scheduled_for: TODAY, someday: 1 }],
    ['deferred-to-tomorrow', { scheduled_for: TODAY, defer_until: TOMORROW }],
    ['done-last-week', { scheduled_for: TODAY, completed_at: addLocalDays(TODAY, -7) }],
  ]
  for (const [id, fields] of rows) {
    mutate(
      db,
      {
        writes: [
          {
            table: 'items',
            key: { id },
            fields: { kind: 'task', title: id, status: 'active', created_at: 1, updated_at: 1 },
          },
          { table: 'task_fields', key: { item_id: id }, fields },
        ],
      },
      'device-1',
      clock,
    )
  }
}

function dayTasks(db: SqliteConnection, dayStart: number, completedSince: number): DayTask[] {
  return db
    .prepare(DAY_TASKS_SQL)
    .all(deferralCutoff(dayStart), completedSince) as unknown as DayTask[]
}

function plans(db: SqliteConnection, a: string, b: string): DayPlanRow[] {
  return db.prepare(DAY_PLANS_SQL).all(a, b) as unknown as DayPlanRow[]
}

describe('on a real database', () => {
  it('DAY_TASKS_SQL: open tasks plus recent completions — never someday, deferred, or deleted', () => {
    const db = freshDb()
    seed(db, createHlcClock('device-1', memoryStore()))
    const ids = dayTasks(db, TODAY, TODAY)
      .map((row) => row.id)
      .sort()
    expect(ids).toEqual(['due-today', 'from-yesterday', 'scheduled-today'])
    // The same deferred task is available when planning the day it's deferred to.
    expect(dayTasks(db, TOMORROW, TODAY).map((row) => row.id)).toContain('deferred-to-tomorrow')
  })

  it('committed top 3 persist in the database and belong to exactly one date', () => {
    const db = freshDb()
    const clock = createHlcClock('device-1', memoryStore())
    seed(db, clock)
    const tasks = dayTasks(db, TODAY, YESTERDAY)
    const picks = ['due-today', 'from-yesterday', 'scheduled-today'].map(
      (id) => tasks.find((row) => row.id === id) as DayTask,
    )

    const plan = planCommitTop3({
      dayStart: TODAY,
      tasks: picks,
      via: 'proposal',
      existing: undefined,
      now: NOW,
    })
    mutate(db, { writes: plan.writes }, 'device-1', clock)

    const todayKey = localDayKey(TODAY)
    const tomorrowKey = localDayKey(TOMORROW)
    expect(committedIds(plans(db, todayKey, todayKey)[0])).toEqual([
      'due-today',
      'from-yesterday',
      'scheduled-today',
    ])
    expect(plans(db, tomorrowKey, tomorrowKey)).toEqual([])
  })

  it('a shutdown, then its undo, replays from the ops log to the same state', () => {
    const db = freshDb()
    const clock = createHlcClock('device-1', memoryStore())
    seed(db, clock)
    const tasks = dayTasks(db, TOMORROW, TODAY)
    const shutdown = planShutdown({
      todayStart: TODAY,
      tomorrowStart: TOMORROW,
      picks: tasks.slice(0, 2),
      existingToday: undefined,
      existingTomorrow: undefined,
      now: NOW,
    })
    mutate(db, { writes: shutdown.writes }, 'device-1', clock)
    const stamped = plans(db, localDayKey(TODAY), localDayKey(TODAY))[0]
    expect(stamped.shutdown_completed_at).toBe(NOW)

    mutate(db, { writes: shutdown.undoWrites }, 'device-1', clock)
    expect(committedIds(plans(db, localDayKey(TOMORROW), localDayKey(TOMORROW))[0])).toEqual([])

    const replayed = freshDb()
    replayOps(replayed, selectAllOps(db))
    const comparison = compareMaterializedTables(db, replayed)
    expect(comparison.ok).toBe(true)
    expect(comparison.tables.find((t) => t.table === 'day_plans')?.liveRowCount).toBe(2)
  })

  it('LAST_ACTIVITY_SQL is the newest op’s time', () => {
    const db = freshDb()
    expect(db.prepare(LAST_ACTIVITY_SQL).all()).toEqual([])
    seed(db, createHlcClock('device-1', memoryStore()))
    const [row] = db.prepare(LAST_ACTIVITY_SQL).all() as { last_active_at: number }[]
    const newest = selectAllOps(db).at(-1)?.created_at
    expect(row.last_active_at).toBe(newest)
  })
})
