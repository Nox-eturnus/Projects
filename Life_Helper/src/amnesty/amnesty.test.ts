// @vitest-environment node
import { DatabaseSync } from 'node:sqlite'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createHlcClock, type HlcState } from '../db/hlc'
import { applyMigrations, type SqliteConnection } from '../db/migrate'
import { compareMaterializedTables, mutate, replayOps, selectAllOps, type Write } from '../db/ops'
import {
  AMNESTY_ELIGIBLE_SQL,
  DAY_TASKS_SQL,
  INBOX_SQL,
  LATEST_SWEEP_SQL,
  RECENT_CAPTURES_SQL,
  SLIPPING_SQL,
  SOMEDAY_SQL,
  SWEPT_ITEMS_SQL,
} from '../routes/taskQueries'
import { addLocalDays, startOfLocalDay } from '../scheduling/localDay'
import { deferralCutoff } from '../scheduling/schedule'
import {
  canUndoSweep,
  DEFAULT_THRESHOLD_DAYS,
  parseThresholdDays,
  planBringBack,
  planSweep,
  planUndoSweep,
  toFtsQuery,
  UNDO_WINDOW_MS,
  untouchedBefore,
  type EligibleTask,
  type SomedayTask,
  type SweepRow,
} from './amnesty'

const DAY_MS = 24 * 60 * 60 * 1000
const HOUR_MS = 60 * 60 * 1000
// "Now" for every test: 10am on a Friday. Real time is faked, because
// mutate() stamps each op with Date.now() — that's how a task gets old.
const TODAY = startOfLocalDay(new Date(2026, 9, 2, 12).getTime())
const NOW = TODAY + 10 * HOUR_MS
const LONG_AGO = TODAY - 60 * DAY_MS

afterEach(() => {
  vi.useRealTimers()
})

function at<T>(time: number, fn: () => T): T {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(time)
  try {
    return fn()
  } finally {
    vi.useRealTimers()
  }
}

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

function write(db: SqliteConnection, clock: Clock, writes: readonly Write[], time = NOW) {
  at(time, () => mutate(db, { writes }, 'device-1', clock))
}

function addTask(
  db: SqliteConnection,
  clock: Clock,
  id: string,
  fields: Record<string, number | null>,
  options: { status?: string; title?: string; createdAt?: number } = {},
) {
  const createdAt = options.createdAt ?? LONG_AGO
  write(
    db,
    clock,
    [
      {
        table: 'items',
        key: { id },
        fields: {
          kind: 'task',
          title: options.title ?? id,
          status: options.status ?? 'active',
          created_at: createdAt,
          updated_at: createdAt,
        },
      },
      { table: 'task_fields', key: { item_id: id }, fields },
    ],
    createdAt,
  )
}

/**
 * A spread of tasks, each created 60 days ago unless noted:
 * - eligible: old and undated; old and planned for a past day; old with a
 *   lapsed deadline; old, in the inbox.
 * - not eligible: touched yesterday; planned for later; due later; done;
 *   already someday; archived; deferred; deleted; created 8 days ago.
 */
function seed() {
  const db = freshDb()
  const clock = createHlcClock('device-1', memoryStore())
  addTask(db, clock, 'old-undated', {})
  addTask(db, clock, 'old-past-plan', { scheduled_for: addLocalDays(TODAY, -45) })
  addTask(db, clock, 'old-lapsed-deadline', { due_at: addLocalDays(TODAY, -40) })
  addTask(db, clock, 'old-inbox', {}, { status: 'inbox' })

  addTask(db, clock, 'touched-yesterday', {})
  write(
    db,
    clock,
    [{ table: 'items', key: { id: 'touched-yesterday' }, fields: { title: 'renamed' } }],
    TODAY - DAY_MS,
  )
  addTask(db, clock, 'planned-later', { scheduled_for: addLocalDays(TODAY, 10) })
  addTask(db, clock, 'planned-today', { scheduled_for: TODAY + 15 * HOUR_MS })
  addTask(db, clock, 'due-later', { due_at: addLocalDays(TODAY, 3) })
  addTask(db, clock, 'done', { completed_at: LONG_AGO + DAY_MS })
  addTask(db, clock, 'already-someday', { someday: 1 })
  addTask(db, clock, 'archived', {}, { status: 'archived' })
  addTask(db, clock, 'deferred', { defer_until: addLocalDays(TODAY, 5) })
  addTask(db, clock, 'deleted', {})
  write(
    db,
    clock,
    [{ table: 'items', key: { id: 'deleted' }, fields: { deleted_at: LONG_AGO } }],
    LONG_AGO,
  )
  addTask(db, clock, 'new', {}, { createdAt: TODAY - 8 * DAY_MS })
  return { db, clock }
}

function eligible(db: SqliteConnection, days = DEFAULT_THRESHOLD_DAYS): EligibleTask[] {
  return db
    .prepare(AMNESTY_ELIGIBLE_SQL)
    .all(deferralCutoff(NOW), TODAY, untouchedBefore(TODAY, days)) as unknown as EligibleTask[]
}

function eligibleIds(db: SqliteConnection, days = DEFAULT_THRESHOLD_DAYS): string[] {
  return eligible(db, days)
    .map((row) => row.id)
    .sort()
}

function someday(db: SqliteConnection, search = ''): SomedayTask[] {
  return db.prepare(SOMEDAY_SQL).all(deferralCutoff(NOW), search) as unknown as SomedayTask[]
}

function latestSweep(db: SqliteConnection): SweepRow | undefined {
  return (db.prepare(LATEST_SWEEP_SQL).all() as unknown as SweepRow[]).at(0)
}

/** Every task's business columns — what "exact prior state" means — without hlc/origin_device. */
function taskState(db: SqliteConnection): unknown[] {
  return db
    .prepare(
      `SELECT items.id, items.title, items.status, items.created_at, items.updated_at, items.deleted_at,
              task_fields.due_at, task_fields.scheduled_for, task_fields.defer_until,
              task_fields.touch_count, task_fields.last_touched_at, task_fields.someday,
              task_fields.completed_at, task_fields.amnesty_sweep_id
       FROM items LEFT JOIN task_fields ON task_fields.item_id = items.id ORDER BY items.id`,
    )
    .all()
}

function sweep(db: SqliteConnection, clock: Clock, days = DEFAULT_THRESHOLD_DAYS) {
  let n = 0
  const plan = planSweep({
    tasks: eligible(db, days),
    thresholdDays: days,
    now: NOW,
    generateId: () => `sweep-${String(++n)}`,
  })
  write(db, clock, plan.writes)
  return plan
}

function undoLatestSweep(db: SqliteConnection, clock: Clock, time = NOW + HOUR_MS) {
  const target = latestSweep(db)
  if (!target) throw new Error('no sweep to undo')
  const itemIds = db
    .prepare(SWEPT_ITEMS_SQL)
    .all(target.id)
    .map((row) => row.item_id as string)
  write(db, clock, planUndoSweep({ sweepId: target.id, itemIds, now: time }).writes, time)
}

function expectReplayMatches(db: SqliteConnection) {
  const replayed = freshDb()
  replayOps(replayed, selectAllOps(db))
  expect(compareMaterializedTables(db, replayed).ok).toBe(true)
}

describe('eligibility (the decay)', () => {
  it('untouched past the threshold, with nothing still ahead of it', () => {
    const { db } = seed()
    expect(eligibleIds(db)).toEqual([
      'old-inbox',
      'old-lapsed-deadline',
      'old-past-plan',
      'old-undated',
    ])
  })

  it('"touched" is the newest change of any kind, not just a reschedule', () => {
    const { db, clock } = seed()
    write(db, clock, [
      { table: 'items', key: { id: 'old-undated' }, fields: { title: 'Edited today' } },
    ])
    expect(eligibleIds(db)).not.toContain('old-undated')
  })

  it('the threshold is configurable: a shorter one reaches newer tasks', () => {
    const { db } = seed()
    expect(eligibleIds(db, 7)).toContain('new')
    // Touched yesterday is recent at any threshold.
    expect(eligibleIds(db, 7)).not.toContain('touched-yesterday')
    expect(eligibleIds(db, 90)).toEqual([])
  })
})

describe('the sweep', () => {
  it('the count shown is exactly what is moved, and nothing else changes', () => {
    const { db, clock } = seed()
    const counted = eligible(db)
    const before = taskState(db)
    const plan = sweep(db, clock)

    const moved = plan.writes.filter((w) => w.table === 'task_fields').map((w) => w.key.item_id)
    expect(moved.sort()).toEqual(counted.map((row) => row.id).sort())
    expect(latestSweep(db)).toMatchObject({ item_count: counted.length, threshold_days: 30 })

    const somedayIds = someday(db)
      .map((row) => row.id)
      .sort()
    expect(somedayIds).toEqual(['already-someday', ...moved].sort())

    // Everything not counted is untouched.
    const after = taskState(db) as { id: string }[]
    const unchanged = (rows: unknown[]) =>
      (rows as { id: string }[]).filter((row) => !moved.includes(row.id))
    expect(unchanged(after)).toEqual(unchanged(before))
  })

  it('only someday and the sweep tag change: dates and status stay as they were', () => {
    const { db, clock } = seed()
    sweep(db, clock)
    const row = someday(db).find((r) => r.id === 'old-past-plan')
    expect(row).toMatchObject({ scheduled_for: addLocalDays(TODAY, -45), status: 'active' })
    const inbox = someday(db).find((r) => r.id === 'old-inbox')
    expect(inbox?.status).toBe('inbox')
  })

  it('swept tasks are in no view and no count — and nothing is left to sweep', () => {
    const { db, clock } = seed()
    const moved = new Set(eligible(db).map((row) => row.id))
    sweep(db, clock)
    const ids = (sql: string, params: unknown[]) =>
      db
        .prepare(sql)
        .all(...params)
        .map((row) => row.id as string)
    const views: [string, unknown[]][] = [
      [DAY_TASKS_SQL, [deferralCutoff(NOW), TODAY]],
      [SLIPPING_SQL, [deferralCutoff(NOW), TODAY]],
      [INBOX_SQL, [deferralCutoff(NOW)]],
      [RECENT_CAPTURES_SQL, [deferralCutoff(NOW)]],
    ]
    for (const [sql, params] of views) {
      for (const id of ids(sql, params)) expect(moved.has(id)).toBe(false)
    }
    expect(eligible(db)).toEqual([])
  })
})

describe('undo (24 hours)', () => {
  it('restores the exact prior state — dates included — and the same eligibility', () => {
    const { db, clock } = seed()
    const before = taskState(db)
    const eligibleBefore = eligibleIds(db)
    sweep(db, clock)
    undoLatestSweep(db, clock)

    expect(taskState(db)).toEqual(before)
    // The sweep and its undo aren't "touching" a task: it's as eligible as before.
    expect(eligibleIds(db)).toEqual(eligibleBefore)
    expect(latestSweep(db)).toBeUndefined()
    expectReplayMatches(db)
  })

  it('leaves alone a task brought back by hand since, and other sweeps’ tasks', () => {
    const { db, clock } = seed()
    sweep(db, clock)
    const broughtBack = someday(db).find((r) => r.id === 'old-undated') as SomedayTask
    write(db, clock, planBringBack(broughtBack, 'inbox', TODAY, NOW + 1).writes, NOW + 1)
    // Set aside again by hand (not by a sweep): undo must not pull it out.
    write(
      db,
      clock,
      [{ table: 'task_fields', key: { item_id: 'old-undated' }, fields: { someday: 1 } }],
      NOW + 2,
    )

    undoLatestSweep(db, clock)
    const stillSomeday = someday(db)
      .map((r) => r.id)
      .sort()
    expect(stillSomeday).toEqual(['already-someday', 'old-undated'])
  })

  it('is offered for 24 hours, and not once undone', () => {
    const sweepRow: SweepRow = {
      id: 's',
      swept_at: NOW,
      threshold_days: 30,
      item_count: 3,
      undone_at: null,
    }
    expect(canUndoSweep(sweepRow, NOW + UNDO_WINDOW_MS - 1)).toBe(true)
    expect(canUndoSweep(sweepRow, NOW + UNDO_WINDOW_MS)).toBe(false)
    expect(canUndoSweep({ ...sweepRow, undone_at: NOW + 1 }, NOW + 2)).toBe(false)
    expect(canUndoSweep(undefined, NOW)).toBe(false)
  })
})

describe('bringing one back', () => {
  it('to today: scheduled for today and active; its decay clock starts again', () => {
    const { db, clock } = seed()
    sweep(db, clock)
    const task = someday(db).find((r) => r.id === 'old-inbox') as SomedayTask
    const plan = planBringBack(task, 'today', TODAY, NOW + 1)
    write(db, clock, plan.writes, NOW + 1)

    const ids = (db.prepare(DAY_TASKS_SQL).all(deferralCutoff(NOW), TODAY) as { id: string }[]).map(
      (row) => row.id,
    )
    expect(ids).toContain('old-inbox')
    expect(eligibleIds(db)).not.toContain('old-inbox')
    expect(someday(db).map((r) => r.id)).not.toContain('old-inbox')
  })

  it('to the inbox: back to triage, dates untouched; undo returns it to someday exactly', () => {
    const { db, clock } = seed()
    sweep(db, clock)
    const inSomeday = taskState(db)
    const task = someday(db).find((r) => r.id === 'old-past-plan') as SomedayTask
    const plan = planBringBack(task, 'inbox', TODAY, NOW + 1)
    write(db, clock, plan.writes, NOW + 1)

    const inbox = db.prepare(INBOX_SQL).all(deferralCutoff(NOW)) as {
      id: string
      scheduled_for: number
    }[]
    expect(inbox.find((row) => row.id === 'old-past-plan')?.scheduled_for).toBe(
      addLocalDays(TODAY, -45),
    )

    write(db, clock, plan.undoWrites, NOW + 2)
    expect(taskState(db)).toEqual(inSomeday)
    expectReplayMatches(db)
  })
})

describe('search', () => {
  it('finds someday tasks by word prefix, every word required', () => {
    const db = freshDb()
    const clock = createHlcClock('device-1', memoryStore())
    addTask(db, clock, 'a', { someday: 1 }, { title: 'Learn sourdough baking' })
    addTask(db, clock, 'b', { someday: 1 }, { title: 'Sort the bookshelf' })
    addTask(db, clock, 'c', {}, { title: 'Sourdough starter (not someday)' })

    const titles = (text: string) => someday(db, toFtsQuery(text)).map((row) => row.title)
    expect(titles('sour')).toEqual(['Learn sourdough baking'])
    expect(titles('so')).toHaveLength(2)
    expect(titles('sort book')).toEqual(['Sort the bookshelf'])
    expect(titles('sort sourdough')).toEqual([])
    expect(titles('')).toHaveLength(2)
  })

  it('nothing typed can be read as FTS5 syntax', () => {
    expect(toFtsQuery('  "sour  dough" ')).toBe('"sour"* "dough"*')
    expect(toFtsQuery('NOT OR AND')).toBe('"NOT"* "OR"* "AND"*')
    expect(toFtsQuery('   ')).toBe('')
    const db = freshDb()
    for (const text of ['"', 'a OR', '(x', '*', 'title:foo', 'NEAR(a b)']) {
      expect(() => someday(db, toFtsQuery(text))).not.toThrow()
    }
  })
})

describe('the threshold setting', () => {
  it('defaults to 30 days, and only accepts a whole number of days from 7 to 365', () => {
    expect(parseThresholdDays(undefined)).toBe(30)
    expect(parseThresholdDays(14)).toBe(14)
    expect(parseThresholdDays(6)).toBe(30)
    expect(parseThresholdDays(366)).toBe(30)
    expect(parseThresholdDays(10.5)).toBe(30)
    expect(parseThresholdDays('20')).toBe(30)
  })

  it('counts whole days back from the start of today', () => {
    expect(untouchedBefore(TODAY, 30)).toBe(addLocalDays(TODAY, -30))
  })
})
