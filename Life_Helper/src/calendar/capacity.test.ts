import { describe, expect, it } from 'vitest'
import type { AllDayEvent, CalendarEvent, TimedEvent } from '../../edge/src/contract.js'
import { startOfLocalDay } from '../scheduling/localDay'
import { withTimeZone } from '../test/timeZone'
import {
  commitmentOf,
  computeCapacity,
  DEFAULT_CAPACITY_SETTINGS,
  eventsOnDay,
  formatMinutes,
  wakingWindow,
  type CapacitySettings,
} from './capacity'
import { parseCapacitySettings } from './capacitySettings'

const at = (h: number, m = 0) => new Date(2026, 8, 11, h, m).getTime() // Fri 11 Sep 2026
const DAY = startOfLocalDay(at(12))

function timed(id: string, start: number, end: number, busy = true): TimedEvent {
  return { id, title: id, allDay: false, start, end, busy }
}

function allDay(id: string, startDate: string, endDate: string): AllDayEvent {
  return { id, title: id, allDay: true, startDate, endDate, busy: true }
}

// 08:00–22:00 (14h) with no buffer, unless a test says otherwise: round numbers.
const PLAIN: CapacitySettings = { wakeStart: '08:00', wakeEnd: '22:00', bufferMinutes: 0 }

describe('computeCapacity: waking hours minus events minus a buffer', () => {
  it('a whole empty day, before waking, is the whole waking window', () => {
    const capacity = computeCapacity([], DAY, at(6), PLAIN)
    expect(capacity).toMatchObject({
      remainingMinutes: 14 * 60,
      freeMinutes: 14 * 60,
      dayOver: false,
    })
  })

  it('counts from now, not from waking, once the day has started', () => {
    expect(computeCapacity([], DAY, at(18), PLAIN).freeMinutes).toBe(4 * 60)
  })

  it('subtracts busy events, clipped to what is left of the day', () => {
    const events = [
      timed('morning', at(9), at(10)), // already past at 11:00 — doesn't count
      timed('lunch', at(12), at(13)),
      timed('late', at(21), at(23)), // only 21:00–22:00 is inside waking hours
    ]
    const capacity = computeCapacity(events, DAY, at(11), PLAIN)
    expect(capacity.busyMinutes).toBe(120)
    expect(capacity.freeMinutes).toBe(11 * 60 - 120)
  })

  it('an event already under way only counts from now', () => {
    expect(computeCapacity([timed('call', at(10), at(12))], DAY, at(11), PLAIN).busyMinutes).toBe(
      60,
    )
  })

  it('overlapping and back-to-back events count once', () => {
    const events = [
      timed('a', at(9), at(11)),
      timed('b', at(10), at(12)),
      timed('c', at(12), at(12, 30)),
      timed('d', at(14), at(15)),
    ]
    expect(computeCapacity(events, DAY, at(8), PLAIN).busyMinutes).toBe(3.5 * 60 + 60)
  })

  it('ignores all-day events and events marked free', () => {
    const events: CalendarEvent[] = [
      allDay('birthday', '2026-09-11', '2026-09-12'),
      timed('focus block (free)', at(9), at(17), false),
    ]
    expect(computeCapacity(events, DAY, at(8), PLAIN).freeMinutes).toBe(14 * 60)
  })

  it('the buffer shrinks with the day: the full buffer at the start, a quarter with a quarter left', () => {
    const settings = { ...PLAIN, bufferMinutes: 120 }
    expect(computeCapacity([], DAY, at(8), settings).bufferMinutes).toBe(120)
    expect(computeCapacity([], DAY, at(18, 30), settings).bufferMinutes).toBe(30)
  })

  it('never goes below zero, and after waking hours the day is over', () => {
    const packed = [timed('all day meeting', at(8), at(22))]
    expect(computeCapacity(packed, DAY, at(9), { ...PLAIN, bufferMinutes: 60 }).freeMinutes).toBe(0)
    expect(computeCapacity([], DAY, at(22, 30), PLAIN)).toMatchObject({
      dayOver: true,
      freeMinutes: 0,
    })
  })

  it('a bedtime after midnight extends the window into the next morning', () => {
    const window = wakingWindow(DAY, { ...PLAIN, wakeStart: '10:00', wakeEnd: '01:30' })
    expect(window.start).toBe(at(10))
    expect(window.end).toBe(new Date(2026, 8, 12, 1, 30).getTime())
  })

  it('waking hours are local wall-clock times on a DST day (a 23-hour day loses nothing awake)', () => {
    withTimeZone('America/New_York', () => {
      const shortDay = new Date(2026, 2, 8).getTime()
      const window = wakingWindow(shortDay, PLAIN)
      expect(new Date(window.start).getHours()).toBe(8)
      expect(new Date(window.end).getHours()).toBe(22)
      expect(computeCapacity([], shortDay, window.start - 1, PLAIN).freeMinutes).toBe(14 * 60)
    })
  })

  it('defaults are 07:00–23:00 with an hour of buffer', () => {
    expect(DEFAULT_CAPACITY_SETTINGS).toEqual({
      wakeStart: '07:00',
      wakeEnd: '23:00',
      bufferMinutes: 60,
    })
  })
})

describe('eventsOnDay', () => {
  it('keeps timed events overlapping the day and all-day events whose dates include it', () => {
    const events: CalendarEvent[] = [
      timed('yesterday', at(9) - 86_400_000, at(10) - 86_400_000),
      timed('overnight', DAY - 3_600_000, DAY + 3_600_000),
      timed('afternoon', at(15), at(16)),
      allDay('trip', '2026-09-10', '2026-09-13'),
      allDay('tomorrow', '2026-09-12', '2026-09-13'),
    ]
    expect(eventsOnDay(events, DAY).map((e) => e.id)).toEqual(['trip', 'overnight', 'afternoon'])
  })

  it('an all-day event is on its date whatever the timezone (Kolkata, +05:30)', () => {
    withTimeZone('Asia/Kolkata', () => {
      const day = new Date(2026, 8, 11).getTime()
      expect(eventsOnDay([allDay('b', '2026-09-11', '2026-09-12')], day)).toHaveLength(1)
      expect(eventsOnDay([allDay('b', '2026-09-12', '2026-09-13')], day)).toHaveLength(0)
    })
  })
})

describe('commitmentOf', () => {
  it('adds up open tasks’ estimates and counts the ones without one', () => {
    expect(
      commitmentOf([
        { estimate_min: 45, completed_at: null },
        { estimate_min: 120, completed_at: null },
        { estimate_min: null, completed_at: null },
        { estimate_min: 60, completed_at: 1 }, // done: needs no more time
      ]),
    ).toEqual({ estimatedMinutes: 165, estimatedCount: 2, unestimatedCount: 1 })
  })
})

describe('formatMinutes', () => {
  it('reads naturally', () => {
    expect([0, 45, 60, 260, -5].map(formatMinutes)).toEqual(['0m', '45m', '1h', '4h 20m', '0m'])
  })
})

describe('parseCapacitySettings', () => {
  it('falls back field by field, so one bad value does not reset the rest', () => {
    expect(parseCapacitySettings(undefined)).toEqual(DEFAULT_CAPACITY_SETTINGS)
    expect(
      parseCapacitySettings({ wakeStart: '06:30', wakeEnd: '25:00', bufferMinutes: -3 }),
    ).toEqual({
      wakeStart: '06:30',
      wakeEnd: '23:00',
      bufferMinutes: 60,
    })
  })
})
