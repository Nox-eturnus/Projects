import { describe, expect, it } from 'vitest'
import { addLocalDays, startOfLocalDay } from '../scheduling/localDay'
import { withTimeZone } from '../test/timeZone'
import { rankCandidates, type DayTask } from '../today/proposal'
import { compareSlipping, findSlipping, isSlipping } from './slipping'

const DAY_MS = 24 * 60 * 60 * 1000
const TODAY = startOfLocalDay(Date.UTC(2026, 9, 2, 12))
const YESTERDAY = addLocalDays(TODAY, -1)
const TOMORROW = addLocalDays(TODAY, 1)

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
    estimate_min: null,
    ...overrides,
  }
}

describe('isSlipping', () => {
  it('a task moved at least once is slipping, dated or not', () => {
    expect(isSlipping(task('a', { touch_count: 1 }), TODAY)).toBe(true)
    expect(isSlipping(task('a', { touch_count: 2, scheduled_for: TODAY }), TODAY)).toBe(true)
  })

  it('a task whose planned day passed is slipping, even if never moved', () => {
    expect(isSlipping(task('a', { scheduled_for: YESTERDAY }), TODAY)).toBe(true)
    expect(isSlipping(task('a', { scheduled_for: TODAY - 1 }), TODAY)).toBe(true)
  })

  it('a task planned for today and never moved is not — today is its day', () => {
    expect(isSlipping(task('a', { scheduled_for: TODAY }), TODAY)).toBe(false)
    expect(isSlipping(task('a', { scheduled_for: TOMORROW - 1 }), TODAY)).toBe(false)
  })

  it('a task deliberately planned for a later day is not, however often it was moved', () => {
    expect(isSlipping(task('a', { touch_count: 5, scheduled_for: TOMORROW }), TODAY)).toBe(false)
  })

  it('an undated task never moved is not: nothing says it was meant for any day', () => {
    expect(isSlipping(task('a'), TODAY)).toBe(false)
  })

  it('a finished task is not', () => {
    expect(
      isSlipping(task('a', { touch_count: 3, scheduled_for: YESTERDAY, completed_at: 5 }), TODAY),
    ).toBe(false)
  })

  it('days are local days — across a DST change too', () => {
    withTimeZone('America/New_York', () => {
      // 2026-03-08 is spring-forward in New York: a 23-hour day.
      const springForward = startOfLocalDay(new Date(2026, 2, 8, 12).getTime())
      const dayBefore = addLocalDays(springForward, -1)
      const lateDayBefore = dayBefore + 23 * 60 * 60 * 1000 + 30 * 60 * 1000 // 23:30
      expect(isSlipping(task('a', { scheduled_for: lateDayBefore }), springForward)).toBe(true)
      const lateThatDay = springForward + 22 * 60 * 60 * 1000 // 23:00 on the 23-hour day
      expect(isSlipping(task('a', { scheduled_for: lateThatDay }), springForward)).toBe(false)
    })
  })
})

describe('ranking: touch count first, age second', () => {
  it('a task moved four times outranks one untouched for twelve days', () => {
    const movedOften = task('moved-often', {
      touch_count: 4,
      last_touched_at: TODAY - DAY_MS,
      scheduled_for: TODAY,
    })
    const leftAlone = task('left-alone', {
      created_at: TODAY - 12 * DAY_MS,
      scheduled_for: TODAY - 12 * DAY_MS,
    })
    expect(findSlipping([leftAlone, movedOften], TODAY).map((t) => t.id)).toEqual([
      'moved-often',
      'left-alone',
    ])
  })

  it('more moves always rank higher, whatever the ages', () => {
    const ranked = findSlipping(
      [
        task('once-ancient', { touch_count: 1, last_touched_at: TODAY - 90 * DAY_MS }),
        task('thrice-recent', { touch_count: 3, last_touched_at: TODAY - DAY_MS }),
        task('twice', { touch_count: 2, last_touched_at: TODAY - 5 * DAY_MS }),
      ],
      TODAY,
    )
    expect(ranked.map((t) => t.id)).toEqual(['thrice-recent', 'twice', 'once-ancient'])
  })

  it('equal moves: the one left alone longest comes first', () => {
    const ranked = findSlipping(
      [
        task('touched-yesterday', { touch_count: 2, last_touched_at: TODAY - DAY_MS }),
        task('touched-last-month', { touch_count: 2, last_touched_at: TODAY - 30 * DAY_MS }),
      ],
      TODAY,
    )
    expect(ranked.map((t) => t.id)).toEqual(['touched-last-month', 'touched-yesterday'])
  })

  it('a never-touched task ages from when it was created', () => {
    const ranked = findSlipping(
      [
        task('created-recently', { scheduled_for: YESTERDAY, created_at: TODAY - 2 * DAY_MS }),
        task('created-long-ago', { scheduled_for: YESTERDAY, created_at: TODAY - 40 * DAY_MS }),
      ],
      TODAY,
    )
    expect(ranked.map((t) => t.id)).toEqual(['created-long-ago', 'created-recently'])
  })

  it('the order is total: full ties fall back to creation time, then id', () => {
    const a = task('a', { touch_count: 1, last_touched_at: 50, created_at: 10 })
    const b = task('b', { touch_count: 1, last_touched_at: 50, created_at: 10 })
    const c = task('c', { touch_count: 1, last_touched_at: 50, created_at: 5 })
    expect([b, a, c].sort(compareSlipping).map((t) => t.id)).toEqual(['c', 'a', 'b'])
  })

  it("leaves out excluded tasks — today's committed three", () => {
    const tasks = [task('in-three', { touch_count: 2 }), task('other', { touch_count: 1 })]
    expect(findSlipping(tasks, TODAY, new Set(['in-three'])).map((t) => t.id)).toEqual(['other'])
  })
})

describe('one definition, shared with Today', () => {
  it("Today's carried-over bucket is exactly the slipping list, in the same order", () => {
    const tasks = [
      task('due', { due_at: TODAY + 1, scheduled_for: TODAY }),
      task('scheduled', { scheduled_for: TODAY }),
      task('moved-twice', { touch_count: 2, last_touched_at: TODAY - DAY_MS }),
      task('from-yesterday', { scheduled_for: YESTERDAY }),
      task('moved-later', { touch_count: 3, scheduled_for: TOMORROW }),
      task('moved-once', { touch_count: 1, last_touched_at: TODAY - 9 * DAY_MS }),
    ]
    const carriedOver = rankCandidates(tasks, TODAY)
      .filter((candidate) => candidate.reason === 'carriedOver')
      .map((candidate) => candidate.task.id)
    // 'due' is slipping-free and sits in its own bucket; everything slipping
    // and not due is carried over, in findSlipping()'s order.
    const slipping = findSlipping(tasks, TODAY)
      .map((t) => t.id)
      .filter((id) => id !== 'due')
    expect(carriedOver).toEqual(slipping)
    expect(carriedOver).toEqual(['moved-twice', 'moved-once', 'from-yesterday'])
  })
})
