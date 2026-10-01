import { describe, expect, it } from 'vitest'
import { addLocalDays, startOfLocalDay } from '../scheduling/localDay'
import {
  describeCandidate,
  describeSlipping,
  describeTask,
  formatAsOf,
  formatLongDate,
  formatShortDate,
  formatSince,
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
    estimate_min: null,
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

  it('says how old something is, and "as of" when, reading naturally either way', () => {
    const now = TODAY + 14 * HOUR_MS
    expect(formatSince(now - 20_000, now)).toBe('just now')
    expect(formatSince(now - 12 * 60_000, now)).toBe('12 min ago')
    expect(formatSince(TODAY + 9 * HOUR_MS, now)).toBe('at 9:00 AM')
    expect(formatSince(addLocalDays(TODAY, -1) + 9 * HOUR_MS, now)).toBe('on Thu 10 Sep at 9:00 AM')
    expect(formatAsOf(TODAY + 9 * HOUR_MS, now)).toBe('9:00 AM')
    expect(formatAsOf(addLocalDays(TODAY, -1) + 9 * HOUR_MS, now)).toBe('Thu 10 Sep, 9:00 AM')
  })

  it('names a small set for button labels', () => {
    expect([1, 2, 3].map(theseN)).toEqual(['this one', 'these two', 'these three'])
  })
})

describe('describeSlipping', () => {
  it('how often it was moved and when it last was — as dates, never "days ago"', () => {
    const lastMoved = addLocalDays(TODAY, -4) + 9 * HOUR_MS // Mon 7 Sep
    expect(describeSlipping(task({ touch_count: 1, last_touched_at: lastMoved }), TODAY)).toBe(
      'Moved once, last on Mon 7 Sep',
    )
    expect(describeSlipping(task({ touch_count: 2, last_touched_at: lastMoved }), TODAY)).toBe(
      'Moved twice, last on Mon 7 Sep',
    )
    expect(describeSlipping(task({ touch_count: 4, last_touched_at: null }), TODAY)).toBe(
      'Moved 4 times',
    )
  })

  it('never moved: the day it was planned for, plus any deadline', () => {
    expect(
      describeSlipping(
        task({ scheduled_for: addLocalDays(TODAY, -2), due_at: TODAY + 17 * HOUR_MS }),
        TODAY,
      ),
    ).toBe('Planned for Wed 9 Sep · Due today')
  })
})
