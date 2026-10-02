// @vitest-environment node
import { DatabaseSync } from 'node:sqlite'
import { describe, expect, it } from 'vitest'
import { createHlcClock, type HlcState } from '../db/hlc'
import { applyMigrations } from '../db/migrate'
import { mutate } from '../db/ops'
import { addLocalDays, localDayKey, startOfLocalDay } from '../scheduling/localDay'
import { withTimeZone } from '../test/timeZone'
import {
  currentStreak,
  evaluateAmnesty,
  evaluateCalendar,
  evaluateColdStart,
  evaluateShutdowns,
  evaluateUsage,
  GATE_ACTIVITY_SQL,
  GATE_SHUTDOWNS_SQL,
  GATE_SWEEPS_SQL,
  lastDays,
  median,
} from './gate'
import { EMPTY_HEALTH, type CalendarHealth, type ColdStart } from './gateLog'

const HOUR_MS = 60 * 60 * 1000
const TODAY = startOfLocalDay(new Date(2026, 9, 20, 12).getTime())
const day = (offset: number) => addLocalDays(TODAY, offset)
const key = (offset: number) => localDayKey(day(offset))

function sample(ms: number, android = true): ColdStart {
  return { at: TODAY, ms, android }
}

describe('1. cold start under 1.5s on Android', () => {
  it('needs at least three Android samples', () => {
    const verdict = evaluateColdStart([sample(400), sample(500)])
    expect(verdict.passed).toBe(false)
    expect(verdict.evidence).toBe('2 of 3 Android cold starts recorded so far')
  })

  it('passes on the median, not the best run', () => {
    expect(evaluateColdStart([sample(900), sample(1_200), sample(2_400)]).passed).toBe(true)
    expect(evaluateColdStart([sample(900), sample(1_600), sample(2_400)]).passed).toBe(false)
  })

  it('a median exactly at the budget is not under it', () => {
    expect(evaluateColdStart([sample(1_500), sample(1_500), sample(1_500)]).passed).toBe(false)
  })

  it('ignores samples from devices that are not Android', () => {
    const verdict = evaluateColdStart([sample(100, false), sample(100, false), sample(100, false)])
    expect(verdict.passed).toBe(false)
    expect(verdict.android).toEqual([])
  })

  it('median of an even count is the mean of the middle two', () => {
    expect(median([4, 1, 3, 2])).toBe(2.5)
  })
})

describe('2. calendar sync survives a week without intervention', () => {
  function health(overrides: Partial<CalendarHealth>): CalendarHealth {
    return { ...EMPTY_HEALTH, ...overrides }
  }

  it('needs a connection and a successful refresh', () => {
    expect(evaluateCalendar(health({}), false).evidence).toBe('not connected on this device')
    expect(evaluateCalendar(health({}), true).evidence).toBe('no successful refresh recorded yet')
  })

  it('passes once a refresh succeeds 7 local days after the first', () => {
    const first = day(-7) + 9 * HOUR_MS
    expect(
      evaluateCalendar(health({ firstOkAt: first, lastOkAt: day(0) + HOUR_MS }), true).passed,
    ).toBe(true)
    // Six days and change is not a week.
    expect(
      evaluateCalendar(health({ firstOkAt: first, lastOkAt: day(-1) + 23 * HOUR_MS }), true).passed,
    ).toBe(false)
  })

  it('fails if anything in the span needed the user — offline and Google hiccups do not count', () => {
    const span = { firstOkAt: day(-8), lastOkAt: day(0) }
    const needed = health({
      ...span,
      days: { [key(-3)]: { ok: 2, problems: { reconnect_required: 1 } } },
    })
    expect(evaluateCalendar(needed, true)).toMatchObject({
      passed: false,
      evidence: `needed you: reconnect_required on ${key(-3)}`,
    })
    const transient = health({
      ...span,
      days: { [key(-3)]: { ok: 2, problems: { offline: 4, upstream_error: 1 } } },
    })
    expect(evaluateCalendar(transient, true).passed).toBe(true)
  })

  it('a problem before the current span started does not count', () => {
    const verdict = evaluateCalendar(
      health({
        firstOkAt: day(-8),
        lastOkAt: day(0),
        days: { [key(-10)]: { ok: 0, problems: { unauthorized: 3 } } },
      }),
      true,
    )
    expect(verdict.passed).toBe(true)
  })

  it('a week is local days, across a DST change too', () => {
    withTimeZone('America/New_York', () => {
      // 2026-11-01 is fall-back in New York: the week containing it has 169 hours.
      const first = new Date(2026, 9, 28, 9).getTime()
      const weekLater = new Date(2026, 10, 4, 0, 30).getTime()
      expect(
        evaluateCalendar({ ...EMPTY_HEALTH, firstOkAt: first, lastOkAt: weekLater }, true).passed,
      ).toBe(true)
    })
  })
})

describe('3. shutdown on at least 5 of 7 days', () => {
  it('counts the 7 days ending today, or ending yesterday — whichever has more', () => {
    const fiveEndingYesterday = new Set([key(-1), key(-2), key(-3), key(-5), key(-7)])
    expect(evaluateShutdowns(fiveEndingYesterday, TODAY)).toMatchObject({
      passed: true,
      evidence: '5 of the last 7 days (needs 5)',
    })
    expect(evaluateShutdowns(new Set([key(0), key(-1), key(-2), key(-3)]), TODAY).passed).toBe(
      false,
    )
  })

  it('lastDays lists local day keys oldest first, ending on the given day', () => {
    expect(lastDays(TODAY, 3)).toEqual([key(-2), key(-1), key(0)])
  })
})

describe('4. usage: 14 consecutive days', () => {
  const days = (offsets: number[]) => new Set(offsets.map(key))

  it('counts back from today when today is active, else from yesterday', () => {
    expect(currentStreak(days([0, -1, -2]), TODAY)).toBe(3)
    expect(currentStreak(days([-1, -2]), TODAY)).toBe(2)
    expect(currentStreak(days([-2, -3]), TODAY)).toBe(0)
  })

  it('a single missed day breaks the streak', () => {
    expect(currentStreak(days([0, -1, -3, -4]), TODAY)).toBe(2)
  })

  it('passes at 14, and only on a phone', () => {
    const fourteen = days(Array.from({ length: 14 }, (_, i) => -i))
    expect(evaluateUsage(fourteen, TODAY, true)).toMatchObject({ passed: true, streak: 14 })
    expect(evaluateUsage(fourteen, TODAY, false).passed).toBe(false)
    const thirteen = days(Array.from({ length: 13 }, (_, i) => -i))
    expect(evaluateUsage(thirteen, TODAY, true).passed).toBe(false)
  })

  it('days are local days across a DST change', () => {
    withTimeZone('America/New_York', () => {
      const today = startOfLocalDay(new Date(2026, 10, 3, 12).getTime())
      const active = new Set(
        Array.from({ length: 5 }, (_, i) => localDayKey(addLocalDays(today, -i))),
      )
      expect(currentStreak(active, today)).toBe(5)
    })
  })
})

describe('5. at least one fresh start kept', () => {
  it('passes with one not undone', () => {
    expect(evaluateAmnesty([]).passed).toBe(false)
    expect(evaluateAmnesty([{ swept_at: day(-2), item_count: 1 }])).toMatchObject({
      passed: true,
      evidence: `1 kept; latest on ${key(-2)}, 1 task`,
    })
  })
})

// --- The gate's queries, on a real database ---------------------------------

function memoryStore() {
  let state: HlcState | undefined
  return {
    load: () => state,
    save: (next: HlcState) => {
      state = next
    },
  }
}

describe('gate queries', () => {
  it('activity is captures and completions since a day, not deleted items', () => {
    const db = new DatabaseSync(':memory:')
    applyMigrations(db)
    const clock = createHlcClock('device-1', memoryStore())
    const write = (writes: Parameters<typeof mutate>[1]['writes']) => {
      mutate(db, { writes }, 'device-1', clock)
    }
    const item = (id: string, createdAt: number, extra: Record<string, number> = {}) => ({
      table: 'items' as const,
      key: { id },
      fields: { kind: 'task', title: id, created_at: createdAt, updated_at: createdAt, ...extra },
    })
    write([item('old', day(-30))])
    write([
      item('captured', day(-2) + HOUR_MS),
      { table: 'task_fields', key: { item_id: 'captured' }, fields: { completed_at: day(-1) } },
    ])
    write([item('deleted', day(-1), { deleted_at: day(-1) })])

    const rows = db.prepare(GATE_ACTIVITY_SQL).all(day(-20)) as { at: number }[]
    expect(rows.map((row) => row.at).sort()).toEqual([day(-2) + HOUR_MS, day(-1)])

    write([
      { table: 'day_plans', key: { day: key(-1) }, fields: { shutdown_completed_at: day(-1) } },
      { table: 'day_plans', key: { day: key(-25) }, fields: { shutdown_completed_at: day(-25) } },
      { table: 'day_plans', key: { day: key(0) }, fields: { committed_at: day(0) } },
    ])
    expect(db.prepare(GATE_SHUTDOWNS_SQL).all(key(-20))).toEqual([{ day: key(-1) }])

    write([
      {
        table: 'amnesty_sweeps',
        key: { id: 's1' },
        fields: { swept_at: day(-3), threshold_days: 30, item_count: 4 },
      },
      {
        table: 'amnesty_sweeps',
        key: { id: 's2' },
        fields: { swept_at: day(-1), threshold_days: 30, item_count: 2, undone_at: day(-1) },
      },
    ])
    expect(db.prepare(GATE_SWEEPS_SQL).all()).toEqual([{ swept_at: day(-3), item_count: 4 }])
  })
})
