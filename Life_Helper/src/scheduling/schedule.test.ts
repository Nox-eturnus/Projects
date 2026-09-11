/// <reference types="node" />
import { readFileSync, readdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { DatabaseSync } from 'node:sqlite'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { createHlcClock, type HlcState } from '../db/hlc'
import { applyMigrations, type SqliteConnection } from '../db/migrate'
import { compareMaterializedTables, mutate, replayOps, selectAllOps, type Write } from '../db/ops'
import { DAY_TASKS_SQL, INBOX_SQL, RECENT_CAPTURES_SQL } from '../routes/taskQueries'
import { withTimeZone } from '../test/timeZone'
import { addLocalDays, startOfLocalDay } from './localDay'
import {
  deferralCutoff,
  isDeferred,
  isForwardReschedule,
  NOT_DEFERRED_SQL,
  planScheduleChange,
  type TaskSchedule,
} from './schedule'

const HOUR_MS = 60 * 60 * 1000

// Fixed in the machine's own zone; the DST suites below pin their own.
const NOW = new Date(2026, 8, 11, 14, 0).getTime() // Fri 11 Sep 2026, 14:00
const TODAY = startOfLocalDay(NOW)
const TOMORROW = addLocalDays(TODAY, 1)
const NEXT_WEEK = addLocalDays(TODAY, 7)
const YESTERDAY = addLocalDays(TODAY, -1)

const BLANK: TaskSchedule = {
  id: 'task-1',
  dueAt: null,
  scheduledFor: null,
  deferUntil: null,
  touchCount: 0,
  lastTouchedAt: null,
}

function fieldsOf(writes: readonly Write[]): Record<string, unknown> {
  expect(writes).toHaveLength(1)
  expect(writes[0]).toMatchObject({ table: 'task_fields', key: { item_id: 'task-1' } })
  return writes[0].fields
}

describe('the three dates are independently settable', () => {
  it('due_at alone', () => {
    const plan = planScheduleChange(BLANK, { dueAt: NEXT_WEEK }, NOW)
    expect(fieldsOf(plan.writes)).toEqual({ due_at: NEXT_WEEK })
    expect(fieldsOf(plan.undoWrites)).toEqual({ due_at: null })
  })

  it('scheduled_for alone', () => {
    const plan = planScheduleChange(BLANK, { scheduledFor: TOMORROW }, NOW)
    expect(fieldsOf(plan.writes)).toEqual({ scheduled_for: TOMORROW })
  })

  it('defer_until alone, stored as the first instant of its day', () => {
    const tomorrow3pm = TOMORROW + 15 * HOUR_MS
    const plan = planScheduleChange(BLANK, { deferUntil: tomorrow3pm }, NOW)
    expect(fieldsOf(plan.writes)).toMatchObject({ defer_until: TOMORROW })
  })

  it('all three at once, each to its own value', () => {
    const plan = planScheduleChange(
      BLANK,
      { dueAt: NEXT_WEEK, scheduledFor: TOMORROW, deferUntil: TOMORROW },
      NOW,
    )
    expect(fieldsOf(plan.writes)).toMatchObject({
      due_at: NEXT_WEEK,
      scheduled_for: TOMORROW,
      defer_until: TOMORROW,
    })
  })

  it('an absent key leaves that date alone; null clears it', () => {
    const task: TaskSchedule = {
      ...BLANK,
      dueAt: NEXT_WEEK,
      scheduledFor: TOMORROW,
      deferUntil: TOMORROW,
    }
    const plan = planScheduleChange(task, { dueAt: null }, NOW)
    expect(fieldsOf(plan.writes)).toEqual({ due_at: null })
    expect(fieldsOf(plan.undoWrites)).toEqual({ due_at: NEXT_WEEK })
  })

  it('setting a date to the value it already has plans no write at all', () => {
    const task: TaskSchedule = { ...BLANK, scheduledFor: TOMORROW }
    const plan = planScheduleChange(task, { scheduledFor: TOMORROW }, NOW)
    expect(plan).toEqual({ writes: [], undoWrites: [], touched: false })
  })

  it('rejects a date that is not a finite number', () => {
    expect(() => planScheduleChange(BLANK, { dueAt: Number.NaN }, NOW)).toThrow(/dueAt/)
    expect(() => planScheduleChange(BLANK, { scheduledFor: Infinity }, NOW)).toThrow(/scheduledFor/)
  })
})

describe('touch_count: reschedules are counted, deadline changes are not', () => {
  const scheduled: TaskSchedule = {
    ...BLANK,
    scheduledFor: TOMORROW,
    touchCount: 2,
    lastTouchedAt: 99,
  }

  it('moving scheduled_for to a later day increments touch_count and stamps last_touched_at', () => {
    const plan = planScheduleChange(scheduled, { scheduledFor: NEXT_WEEK }, NOW)
    expect(plan.touched).toBe(true)
    expect(fieldsOf(plan.writes)).toEqual({
      scheduled_for: NEXT_WEEK,
      touch_count: 3,
      last_touched_at: NOW,
    })
  })

  it('undo restores touch_count and last_touched_at exactly', () => {
    const plan = planScheduleChange(scheduled, { scheduledFor: NEXT_WEEK }, NOW)
    expect(fieldsOf(plan.undoWrites)).toEqual({
      scheduled_for: TOMORROW,
      touch_count: 2,
      last_touched_at: 99,
    })
  })

  it('scheduling an unscheduled task for the first time is planning, not a reschedule', () => {
    expect(planScheduleChange(BLANK, { scheduledFor: NEXT_WEEK }, NOW).touched).toBe(false)
  })

  it('a later time on the same day is not a reschedule', () => {
    const plan = planScheduleChange(scheduled, { scheduledFor: TOMORROW + 18 * HOUR_MS }, NOW)
    expect(plan.touched).toBe(false)
    expect(fieldsOf(plan.writes)).toEqual({ scheduled_for: TOMORROW + 18 * HOUR_MS })
  })

  it('pulling a task in to an earlier day is not a reschedule', () => {
    expect(planScheduleChange(scheduled, { scheduledFor: TODAY }, NOW).touched).toBe(false)
  })

  it('an overdue task moved to today is a reschedule', () => {
    const overdue: TaskSchedule = { ...BLANK, scheduledFor: YESTERDAY }
    expect(planScheduleChange(overdue, { scheduledFor: TODAY }, NOW).touched).toBe(true)
  })

  it('clearing scheduled_for counts — clear-then-reset would otherwise dodge the count', () => {
    const plan = planScheduleChange(scheduled, { scheduledFor: null }, NOW)
    expect(fieldsOf(plan.writes)).toEqual({
      scheduled_for: null,
      touch_count: 3,
      last_touched_at: NOW,
    })
  })

  it('moving due_at, however far, never touches', () => {
    const due: TaskSchedule = { ...scheduled, dueAt: TOMORROW }
    const plan = planScheduleChange(due, { dueAt: addLocalDays(TODAY, 60) }, NOW)
    expect(plan.touched).toBe(false)
    expect(fieldsOf(plan.writes)).toEqual({ due_at: addLocalDays(TODAY, 60) })
    expect(planScheduleChange(due, { dueAt: null }, NOW).touched).toBe(false)
  })

  it('one move that also changes due_at still counts exactly once', () => {
    const plan = planScheduleChange(
      scheduled,
      { dueAt: NEXT_WEEK, scheduledFor: addLocalDays(TODAY, 3) },
      NOW,
    )
    expect(fieldsOf(plan.writes)).toMatchObject({ touch_count: 3 })
  })

  it('rescheduling and deferring in one move counts once, not twice', () => {
    const plan = planScheduleChange(
      scheduled,
      { scheduledFor: NEXT_WEEK, deferUntil: NEXT_WEEK },
      NOW,
    )
    expect(fieldsOf(plan.writes)).toMatchObject({ touch_count: 3 })
  })

  it('isForwardReschedule is day-granular and treats null as "not yet planned"', () => {
    expect(isForwardReschedule(null, TOMORROW)).toBe(false)
    expect(isForwardReschedule(null, null)).toBe(false)
    expect(isForwardReschedule(TOMORROW, null)).toBe(true)
    expect(isForwardReschedule(TOMORROW, TOMORROW + 5 * HOUR_MS)).toBe(false)
    expect(isForwardReschedule(TOMORROW, addLocalDays(TOMORROW, 1))).toBe(true)
  })
})

describe('touch_count: deferring counts like rescheduling', () => {
  it('deferring a visible task to a later day is a deferral', () => {
    const plan = planScheduleChange(BLANK, { deferUntil: NEXT_WEEK }, NOW)
    expect(plan.touched).toBe(true)
    expect(fieldsOf(plan.writes)).toEqual({
      defer_until: NEXT_WEEK,
      touch_count: 1,
      last_touched_at: NOW,
    })
  })

  it('pushing an existing deferral later counts again', () => {
    const deferred: TaskSchedule = { ...BLANK, deferUntil: TOMORROW, touchCount: 1 }
    expect(planScheduleChange(deferred, { deferUntil: NEXT_WEEK }, NOW).touched).toBe(true)
  })

  it('pulling a deferral in, or lifting it, does not count', () => {
    const deferred: TaskSchedule = { ...BLANK, deferUntil: NEXT_WEEK, touchCount: 1 }
    expect(planScheduleChange(deferred, { deferUntil: TOMORROW }, NOW).touched).toBe(false)
    expect(planScheduleChange(deferred, { deferUntil: null }, NOW).touched).toBe(false)
  })

  it('"deferring" to today or earlier hides nothing, so it does not count', () => {
    expect(planScheduleChange(BLANK, { deferUntil: TODAY }, NOW).touched).toBe(false)
    expect(planScheduleChange(BLANK, { deferUntil: YESTERDAY }, NOW).touched).toBe(false)
  })

  it('re-deferring a task whose old deferral already lapsed is a fresh deferral', () => {
    const lapsed: TaskSchedule = { ...BLANK, deferUntil: addLocalDays(TODAY, -10) }
    expect(planScheduleChange(lapsed, { deferUntil: TOMORROW }, NOW).touched).toBe(true)
  })
})

describe('deferral visibility', () => {
  it('a task is hidden before its defer date and visible from the first instant of it', () => {
    expect(isDeferred(TOMORROW, NOW)).toBe(true)
    expect(isDeferred(TOMORROW, TOMORROW - 1)).toBe(true)
    expect(isDeferred(TOMORROW, TOMORROW)).toBe(false)
    expect(isDeferred(TODAY, NOW)).toBe(false)
    expect(isDeferred(null, NOW)).toBe(false)
  })

  it('a stored defer_until carrying a time of day still reappears at the start of that day', () => {
    // Not something planScheduleChange writes, but a synced or imported row
    // could carry one — it's a date either way.
    expect(isDeferred(TOMORROW + 15 * HOUR_MS, TOMORROW + 1)).toBe(false)
  })
})

describe('timezone handling across a DST boundary', () => {
  it('New York spring-forward: 1 hour later but past midnight is a reschedule', () => {
    withTimeZone('America/New_York', () => {
      const now = new Date(2026, 2, 6, 10).getTime()
      const task: TaskSchedule = { ...BLANK, scheduledFor: new Date(2026, 2, 7, 23, 30).getTime() }
      const plan = planScheduleChange(
        task,
        { scheduledFor: new Date(2026, 2, 8, 0, 30).getTime() },
        now,
      )
      expect(plan.touched).toBe(true)
    })
  })

  it('New York spring-forward: 22 hours later on the 23-hour day is the same day', () => {
    withTimeZone('America/New_York', () => {
      const now = new Date(2026, 2, 6, 10).getTime()
      const start = new Date(2026, 2, 8, 0, 30).getTime()
      const end = new Date(2026, 2, 8, 23, 30).getTime()
      expect(end - start).toBe(22 * HOUR_MS)
      const task: TaskSchedule = { ...BLANK, scheduledFor: start }
      expect(planScheduleChange(task, { scheduledFor: end }, now).touched).toBe(false)
    })
  })

  it('New York fall-back: a full 24 hours later on the 25-hour day is still the same day', () => {
    withTimeZone('America/New_York', () => {
      const now = new Date(2026, 9, 30, 10).getTime()
      const start = new Date(2026, 10, 1, 0, 15).getTime()
      const end = new Date(2026, 10, 1, 23, 15).getTime()
      expect(end - start).toBe(24 * HOUR_MS)
      const task: TaskSchedule = { ...BLANK, scheduledFor: start }
      expect(planScheduleChange(task, { scheduledFor: end }, now).touched).toBe(false)
    })
  })

  it('Kolkata: 03:00 to 07:00 on one local day is not a reschedule, though UTC days differ', () => {
    withTimeZone('Asia/Kolkata', () => {
      const now = new Date(2026, 8, 10, 12).getTime()
      const task: TaskSchedule = { ...BLANK, scheduledFor: new Date(2026, 8, 11, 3).getTime() }
      const plan = planScheduleChange(
        task,
        { scheduledFor: new Date(2026, 8, 11, 7).getTime() },
        now,
      )
      expect(plan.touched).toBe(false)
    })
  })

  it('a defer date on the spring-forward day is stored as that day’s local midnight', () => {
    withTimeZone('America/New_York', () => {
      const now = new Date(2026, 2, 6, 10).getTime()
      const plan = planScheduleChange(
        BLANK,
        { deferUntil: new Date(2026, 2, 8, 15).getTime() },
        now,
      )
      expect(fieldsOf(plan.writes)).toMatchObject({ defer_until: new Date(2026, 2, 8).getTime() })
    })
  })

  it('a task deferred to the day after spring-forward reappears at local midnight, 23h after the prior one', () => {
    withTimeZone('America/New_York', () => {
      const deferUntil = new Date(2026, 2, 9).getTime()
      const shortDayStart = new Date(2026, 2, 8).getTime()
      expect(deferralCutoff(shortDayStart)).toBe(deferUntil)
      expect(deferUntil - shortDayStart).toBe(23 * HOUR_MS)
      expect(isDeferred(deferUntil, new Date(2026, 2, 8, 23, 59, 59, 999).getTime())).toBe(true)
      expect(isDeferred(deferUntil, deferUntil)).toBe(false)
    })
  })

  it('São Paulo 2018: a task deferred to the day with no midnight reappears at its 01:00', () => {
    withTimeZone('America/Sao_Paulo', () => {
      const now = new Date(2018, 10, 2, 12).getTime()
      const plan = planScheduleChange(
        BLANK,
        { deferUntil: new Date(2018, 10, 4, 12).getTime() },
        now,
      )
      const stored = fieldsOf(plan.writes).defer_until as number
      expect(new Date(stored).getHours()).toBe(1)
      expect(isDeferred(stored, new Date(2018, 10, 3, 23, 59).getTime())).toBe(true)
      expect(isDeferred(stored, stored)).toBe(false)
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

function createTask(db: SqliteConnection, clock: ReturnType<typeof createHlcClock>, id: string) {
  mutate(
    db,
    {
      writes: [
        {
          table: 'items',
          key: { id },
          fields: { kind: 'task', title: id, status: 'inbox', created_at: 1, updated_at: 1 },
        },
        { table: 'task_fields', key: { item_id: id }, fields: {} },
      ],
    },
    'device-1',
    clock,
  )
}

function readSchedule(db: SqliteConnection, id: string): TaskSchedule {
  const row = db
    .prepare(
      `SELECT due_at, scheduled_for, defer_until, touch_count, last_touched_at
       FROM task_fields WHERE item_id = ?`,
    )
    .all(id)[0] as {
    due_at: number | null
    scheduled_for: number | null
    defer_until: number | null
    touch_count: number
    last_touched_at: number | null
  }
  return {
    id,
    dueAt: row.due_at,
    scheduledFor: row.scheduled_for,
    deferUntil: row.defer_until,
    touchCount: row.touch_count,
    lastTouchedAt: row.last_touched_at,
  }
}

describe('through mutate() on a real database', () => {
  it('each move increments touch_count exactly once, with exactly one touch_count op per move', () => {
    const db = freshDb()
    const clock = createHlcClock('device-1', memoryStore())
    createTask(db, clock, 'task-1')

    const moves: [number, number][] = [
      [TODAY, NOW], // first scheduling — not counted
      [TOMORROW, NOW + 1], // counted
      [TOMORROW + 3 * HOUR_MS, NOW + 2], // same day — not counted
      [NEXT_WEEK, NOW + 3], // counted
      [addLocalDays(TODAY, 3), NOW + 4], // pulled in — not counted
      [addLocalDays(TODAY, 9), NOW + 5], // counted
    ]
    for (const [scheduledFor, at] of moves) {
      const plan = planScheduleChange(readSchedule(db, 'task-1'), { scheduledFor }, at)
      mutate(db, { writes: plan.writes }, 'device-1', clock)
    }

    const final = readSchedule(db, 'task-1')
    expect(final.touchCount).toBe(3)
    expect(final.lastTouchedAt).toBe(NOW + 5)
    const touchOps = selectAllOps(db).filter((op) => op.field === 'touch_count')
    expect(touchOps.map((op) => op.value)).toEqual(['1', '2', '3'])
  })

  it('moving due_at on a real row leaves touch_count and last_touched_at untouched', () => {
    const db = freshDb()
    const clock = createHlcClock('device-1', memoryStore())
    createTask(db, clock, 'task-1')

    for (const dueAt of [TOMORROW, NEXT_WEEK, addLocalDays(TODAY, 30)]) {
      const plan = planScheduleChange(readSchedule(db, 'task-1'), { dueAt }, NOW)
      mutate(db, { writes: plan.writes }, 'device-1', clock)
    }

    expect(readSchedule(db, 'task-1')).toMatchObject({
      dueAt: addLocalDays(TODAY, 30),
      touchCount: 0,
      lastTouchedAt: null,
    })
  })

  it('undo puts the row back exactly, and the ops log still replays to the same state', () => {
    const db = freshDb()
    const clock = createHlcClock('device-1', memoryStore())
    createTask(db, clock, 'task-1')
    const first = planScheduleChange(readSchedule(db, 'task-1'), { scheduledFor: TOMORROW }, NOW)
    mutate(db, { writes: first.writes }, 'device-1', clock)
    const before = readSchedule(db, 'task-1')

    const move = planScheduleChange(
      before,
      { scheduledFor: NEXT_WEEK, deferUntil: NEXT_WEEK, dueAt: NEXT_WEEK },
      NOW + 1,
    )
    mutate(db, { writes: move.writes }, 'device-1', clock)
    expect(readSchedule(db, 'task-1').touchCount).toBe(1)

    mutate(db, { writes: move.undoWrites }, 'device-1', clock)
    expect(readSchedule(db, 'task-1')).toEqual(before)

    const replayed = freshDb()
    replayOps(replayed, selectAllOps(db))
    expect(compareMaterializedTables(db, replayed).ok).toBe(true)
  })
})

// --- "Deferred items are absent from every view until their date" ---------

// Each view's SQL, and the params it's bound with for a given `now`: the
// deferral cutoff first, then whatever else that query takes.
const TASK_VIEW_QUERIES: Record<string, [string, (now: number) => unknown[]]> = {
  INBOX_SQL: [INBOX_SQL, (now) => [deferralCutoff(now)]],
  RECENT_CAPTURES_SQL: [RECENT_CAPTURES_SQL, (now) => [deferralCutoff(now)]],
  DAY_TASKS_SQL: [DAY_TASKS_SQL, (now) => [deferralCutoff(now), startOfLocalDay(now)]],
}

describe('every task view hides deferred items until their date', () => {
  function seed(): SqliteConnection {
    const db = freshDb()
    const clock = createHlcClock('device-1', memoryStore())
    for (const id of ['visible', 'deferred', 'lapsed', 'deferred-to-today']) {
      createTask(db, clock, id)
    }
    const defer = (id: string, deferUntil: number) => {
      const plan = planScheduleChange(readSchedule(db, id), { deferUntil }, NOW)
      mutate(db, { writes: plan.writes }, 'device-1', clock)
    }
    defer('deferred', TOMORROW)
    defer('lapsed', YESTERDAY)
    defer('deferred-to-today', TODAY)
    // A task with no task_fields row at all (the LEFT JOIN's NULL side).
    mutate(
      db,
      {
        writes: [
          {
            table: 'items',
            key: { id: 'no-task-fields' },
            fields: { kind: 'task', title: 'x', status: 'inbox', created_at: 2, updated_at: 2 },
          },
        ],
      },
      'device-1',
      clock,
    )
    return db
  }

  function idsAt(db: SqliteConnection, name: string, now: number): string[] {
    const [sql, params] = TASK_VIEW_QUERIES[name]
    return db
      .prepare(sql)
      .all(...params(now))
      .map((row) => row.id as string)
      .sort()
  }

  for (const name of Object.keys(TASK_VIEW_QUERIES)) {
    it(`${name}: absent the day before, present from the start of the defer date`, () => {
      const db = seed()
      expect(idsAt(db, name, NOW)).toEqual([
        'deferred-to-today',
        'lapsed',
        'no-task-fields',
        'visible',
      ])
      expect(idsAt(db, name, TOMORROW - 1)).not.toContain('deferred')
      expect(idsAt(db, name, TOMORROW)).toContain('deferred')
    })
  }

  it('the inbox query hands triage every field planScheduleChange needs', () => {
    const db = seed()
    const row = db.prepare(INBOX_SQL).all(deferralCutoff(NOW))[0]
    for (const column of [
      'due_at',
      'scheduled_for',
      'defer_until',
      'touch_count',
      'last_touched_at',
    ]) {
      expect(row).toHaveProperty(column)
    }
    // COALESCEd, so a task with no task_fields row still counts from 0.
    const bare = db
      .prepare(INBOX_SQL)
      .all(deferralCutoff(NOW))
      .find((r) => r.id === 'no-task-fields')
    expect(bare?.touch_count).toBe(0)
  })
})

describe('no task view anywhere in src/ skips the deferral filter', () => {
  // A static guard, same idea as schema.test.ts's DELETE FROM scan: any SQL
  // string that selects tasks must interpolate NOT_DEFERRED_SQL, so a view
  // added in a later part (Today, slipping, search) can't quietly show
  // deferred items. It finds the template literal around each
  // `kind = 'task'`, so it covers queries written the way this codebase
  // writes them — not every conceivable spelling of one.
  const here = dirname(fileURLToPath(import.meta.url))
  const srcDir = join(here, '..')

  function walk(dir: string): string[] {
    return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
      const full = join(dir, entry.name)
      if (entry.isDirectory()) return walk(full)
      return /\.tsx?$/.test(entry.name) && !/\.test\.tsx?$/.test(entry.name) ? [full] : []
    })
  }

  function taskQueriesIn(source: string): string[] {
    const found: string[] = []
    for (const match of source.matchAll(/kind\s*=\s*'task'/g)) {
      const open = source.lastIndexOf('`', match.index)
      const close = source.indexOf('`', match.index)
      if (open === -1 || close === -1) continue
      const literal = source.slice(open, close + 1)
      if (/\bSELECT\b/i.test(literal)) found.push(literal)
    }
    return found
  }

  const queries = walk(srcDir).flatMap((file) =>
    taskQueriesIn(readFileSync(file, 'utf8')).map((sql) => ({ file, sql })),
  )

  it('found the task views that exist today (so this scan is not vacuous)', () => {
    expect(queries.length).toBeGreaterThanOrEqual(Object.keys(TASK_VIEW_QUERIES).length)
  })

  it('every one of them interpolates NOT_DEFERRED_SQL', () => {
    const missing = queries.filter(({ sql }) => !sql.includes('${NOT_DEFERRED_SQL}'))
    expect(missing.map(({ file }) => file)).toEqual([])
  })

  it('NOT_DEFERRED_SQL is a single-placeholder boolean over task_fields.defer_until', () => {
    expect(NOT_DEFERRED_SQL.match(/\?/g)).toHaveLength(1)
    expect(NOT_DEFERRED_SQL).toContain('task_fields.defer_until')
  })
})
