import { describe, expect, it } from 'vitest'
import { addLocalDays, startOfLocalDay } from '../scheduling/localDay'
import { withTimeZone } from '../test/timeZone'
import { proposeTop3, rankCandidates, type DayTask } from './proposal'

const HOUR_MS = 60 * 60 * 1000
const NOW = new Date(2026, 8, 11, 14, 0).getTime() // Fri 11 Sep 2026, 14:00
const TODAY = startOfLocalDay(NOW)
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
    ...overrides,
  }
}

function ids(tasks: readonly DayTask[], dayStart = TODAY): string[] {
  return rankCandidates(tasks, dayStart).map((candidate) => candidate.task.id)
}

describe('rankCandidates: due today, then carried over, then oldest scheduled', () => {
  it('orders the three sources in that order', () => {
    const tasks = [
      task('scheduled', { scheduled_for: TODAY + 9 * HOUR_MS }),
      task('carried', { scheduled_for: YESTERDAY }),
      task('due', { due_at: TODAY + 17 * HOUR_MS }),
    ]
    expect(rankCandidates(tasks, TODAY).map((c) => [c.task.id, c.reason])).toEqual([
      ['due', 'due'],
      ['carried', 'carriedOver'],
      ['scheduled', 'scheduled'],
    ])
  })

  it('due: earliest deadline first, including one already passed; not tomorrow’s', () => {
    const tasks = [
      task('due-5pm', { due_at: TODAY + 17 * HOUR_MS }),
      task('due-yesterday', { due_at: YESTERDAY + 12 * HOUR_MS }),
      task('due-tomorrow', { due_at: TOMORROW + HOUR_MS }),
      task('due-9am', { due_at: TODAY + 9 * HOUR_MS }),
    ]
    expect(ids(tasks)).toEqual(['due-yesterday', 'due-9am', 'due-5pm'])
  })

  it('a deadline puts a task in the due bucket even if it is scheduled later', () => {
    const tasks = [
      task('due-but-scheduled-next-week', { due_at: TODAY, scheduled_for: addLocalDays(TODAY, 7) }),
    ]
    expect(rankCandidates(tasks, TODAY).at(0)?.reason).toBe('due')
  })

  it('carried over: most-rescheduled first, then longest untouched', () => {
    const tasks = [
      task('moved-once', { touch_count: 1, last_touched_at: 500 }),
      task('moved-four-times', { touch_count: 4, last_touched_at: 900 }),
      task('moved-once-long-ago', { touch_count: 1, last_touched_at: 100 }),
      task('missed-yesterday', { scheduled_for: YESTERDAY, created_at: 50 }),
    ]
    expect(ids(tasks)).toEqual([
      'moved-four-times',
      'moved-once-long-ago',
      'moved-once',
      'missed-yesterday',
    ])
  })

  it('a task moved to a later day on purpose is not carried over', () => {
    const tasks = [
      task('pushed-to-next-week', { touch_count: 3, scheduled_for: addLocalDays(TODAY, 7) }),
    ]
    expect(ids(tasks)).toEqual([])
  })

  it('scheduled for today: oldest task first, whatever its time', () => {
    const tasks = [
      task('new-9am', { scheduled_for: TODAY + 9 * HOUR_MS, created_at: 3_000 }),
      task('old-6pm', { scheduled_for: TODAY + 18 * HOUR_MS, created_at: 1_000 }),
      task('mid', { scheduled_for: TODAY, created_at: 2_000 }),
    ]
    expect(ids(tasks)).toEqual(['old-6pm', 'mid', 'new-9am'])
  })

  it('each task appears once, under the first source it qualifies for', () => {
    const tasks = [task('both', { due_at: TODAY + HOUR_MS, scheduled_for: TODAY, touch_count: 2 })]
    expect(rankCandidates(tasks, TODAY)).toEqual([{ task: tasks[0], reason: 'due' }])
  })

  it('leaves out completed tasks, undated never-moved tasks, and tomorrow’s', () => {
    const tasks = [
      task('done', { scheduled_for: TODAY, completed_at: NOW }),
      task('undated'),
      task('tomorrow', { scheduled_for: TOMORROW }),
    ]
    expect(ids(tasks)).toEqual([])
  })

  it('judges "today" by local days across a DST boundary', () => {
    withTimeZone('America/New_York', () => {
      const shortDay = new Date(2026, 2, 8).getTime() // 23 hours long
      const tasks = [
        task('late-on-the-short-day', { scheduled_for: new Date(2026, 2, 8, 23, 30).getTime() }),
        task('first-thing-next-day', { scheduled_for: new Date(2026, 2, 9, 0, 15).getTime() }),
      ]
      expect(ids(tasks, shortDay)).toEqual(['late-on-the-short-day'])
    })
  })
})

describe('proposeTop3', () => {
  const tasks = ['a', 'b', 'c', 'd', 'e'].map((id, i) =>
    task(id, { scheduled_for: TODAY, created_at: i }),
  )

  it('is the first three candidates', () => {
    expect(proposeTop3(tasks, TODAY).map((c) => c.task.id)).toEqual(['a', 'b', 'c'])
  })

  it('a swap excludes one and the next in line moves up', () => {
    expect(proposeTop3(tasks, TODAY, new Set(['b'])).map((c) => c.task.id)).toEqual(['a', 'c', 'd'])
  })

  it('proposes fewer than three when fewer exist, never padding with non-candidates', () => {
    expect(proposeTop3([tasks[0], task('undated')], TODAY).map((c) => c.task.id)).toEqual(['a'])
  })
})
