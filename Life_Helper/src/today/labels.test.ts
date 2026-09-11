import { describe, expect, it } from 'vitest'
import { addLocalDays, startOfLocalDay } from '../scheduling/localDay'
import {
  describeCandidate,
  describeTask,
  formatLongDate,
  formatShortDate,
  formatTime,
  theseN,
} from './labels'
import type { DayTask } from './proposal'

const HOUR_MS = 60 * 60 * 1000
const TODAY = startOfLocalDay(new Date(2026, 8, 11, 12).getTime()) // Fri 11 Sep 2026

function task(overrides: Partial<DayTask> = {}): DayTask {
  return {
    id: 't',
    title: 't',
    status: 'active',
    created_at: 1,
    due_at: null,
    scheduled_for: null,
    defer_until: null,
    touch_count: 0,
    last_touched_at: null,
    completed_at: null,
    ...overrides,
  }
}

describe('labels', () => {
  it('formats dates and times the same on every device', () => {
    expect(formatLongDate(TODAY)).toBe('Friday 11 September')
    expect(formatShortDate(addLocalDays(TODAY, -3))).toBe('Tue 8 Sep')
    expect(formatTime(TODAY + 18 * HOUR_MS)).toBe('6:00 PM')
    expect(formatTime(TODAY + 30 * 60 * 1000)).toBe('12:30 AM')
    expect(formatTime(TODAY)).toBeNull()
  })

  it('describes a task by its time, where it came from, and its deadline', () => {
    expect(describeTask(task({ scheduled_for: TODAY + 18 * HOUR_MS }), TODAY)).toBe('6:00 PM')
    expect(describeTask(task({ scheduled_for: TODAY }), TODAY)).toBe('')
    expect(
      describeTask(task({ scheduled_for: addLocalDays(TODAY, -3), due_at: TODAY }), TODAY),
    ).toBe('From Tue 8 Sep · Due today')
  })

  it('explains a proposal without guilt words', () => {
    const due = describeCandidate({ task: task({ due_at: TODAY + HOUR_MS }), reason: 'due' }, TODAY)
    const carried = describeCandidate({ task: task(), reason: 'carriedOver' }, TODAY)
    const scheduled = describeCandidate(
      { task: task({ scheduled_for: TODAY + 18 * HOUR_MS }), reason: 'scheduled' },
      TODAY,
    )
    expect([due, carried, scheduled]).toEqual(['Due today', 'Carried over', 'Scheduled, 6:00 PM'])
    for (const text of [due, carried, scheduled]) {
      expect(text).not.toMatch(/overdue|late|missed|behind|slipp/i)
    }
  })

  it('names a small set for button labels', () => {
    expect([1, 2, 3].map(theseN)).toEqual(['this one', 'these two', 'these three'])
  })
})
