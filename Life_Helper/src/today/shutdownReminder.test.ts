import { describe, expect, it } from 'vitest'
import { withTimeZone } from '../test/timeZone'
import {
  DEFAULT_SHUTDOWN_TIME,
  EVENING_SHUTDOWN_SLOT,
  isShutdownDue,
  isValidShutdownTime,
  shutdownReminderAt,
} from './shutdownReminder'

const at = (h: number, m = 0) => new Date(2026, 8, 11, h, m).getTime()

describe('shutdown reminder', () => {
  it('defaults to 8pm, and deep-links to the shutdown route', () => {
    expect(DEFAULT_SHUTDOWN_TIME).toBe('20:00')
    expect(EVENING_SHUTDOWN_SLOT.route).toBe('/shutdown')
    expect(EVENING_SHUTDOWN_SLOT.priority).toBe(1)
  })

  it('is the configured time on the current local date', () => {
    expect(shutdownReminderAt(at(9), '20:00')).toBe(at(20))
    expect(shutdownReminderAt(at(23, 59), '21:30')).toBe(at(21, 30))
  })

  it('is due from that time until midnight, unless tonight’s shutdown is done', () => {
    expect(isShutdownDue(at(19, 59), '20:00', false)).toBe(false)
    expect(isShutdownDue(at(20, 0), '20:00', false)).toBe(true)
    expect(isShutdownDue(at(23, 59), '20:00', false)).toBe(true)
    expect(isShutdownDue(at(21, 0), '20:00', true)).toBe(false)
  })

  it('accepts only 24-hour HH:MM, and falls back to 8pm on anything else', () => {
    expect(isValidShutdownTime('07:05')).toBe(true)
    expect(isValidShutdownTime('23:59')).toBe(true)
    for (const bad of ['24:00', '8pm', '8:00', '20:60', '']) {
      expect(isValidShutdownTime(bad)).toBe(false)
    }
    expect(shutdownReminderAt(at(9), 'garbage')).toBe(at(20))
  })

  it('20:00 is 20:00 local on a DST day, not 24 hours after the previous one', () => {
    withTimeZone('America/New_York', () => {
      const sat = shutdownReminderAt(new Date(2026, 2, 7, 9).getTime(), '20:00')
      const sun = shutdownReminderAt(new Date(2026, 2, 8, 9).getTime(), '20:00')
      expect(new Date(sun).getHours()).toBe(20)
      expect(sun - sat).toBe(23 * 60 * 60 * 1000)
    })
  })
})
