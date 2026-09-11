import { describe, expect, it } from 'vitest'
import { withTimeZone } from '../test/timeZone'
import {
  addLocalDays,
  atLocalTimeOf,
  compareLocalDays,
  localDayKey,
  localDayOrdinal,
  startOfLocalDay,
  startOfNextLocalDay,
} from './localDay'

const HOUR_MS = 60 * 60 * 1000

// Real transitions, 2026 unless noted:
// - America/New_York springs forward Sun 8 Mar (02:00 → 03:00, a 23-hour
//   day) and falls back Sun 1 Nov (02:00 → 01:00, a 25-hour day).
// - Europe/London springs forward Sun 29 Mar (01:00 → 02:00).
// - America/Sao_Paulo sprang forward at midnight on Sun 4 Nov 2018, so
//   00:00 didn't exist that day at all.
// - Asia/Kolkata has no DST but a +05:30 offset, so its day boundaries
//   never line up with UTC's.
const NEW_YORK = 'America/New_York'
const LONDON = 'Europe/London'
const SAO_PAULO = 'America/Sao_Paulo'
const KOLKATA = 'Asia/Kolkata'

describe('startOfLocalDay / startOfNextLocalDay across DST', () => {
  it('a spring-forward day is 23 hours long (New York)', () => {
    withTimeZone(NEW_YORK, () => {
      const noon = new Date(2026, 2, 8, 12).getTime()
      const start = startOfLocalDay(noon)
      expect(start).toBe(new Date(2026, 2, 8).getTime())
      expect(startOfNextLocalDay(noon) - start).toBe(23 * HOUR_MS)
    })
  })

  it('a fall-back day is 25 hours long (New York)', () => {
    withTimeZone(NEW_YORK, () => {
      const noon = new Date(2026, 10, 1, 12).getTime()
      expect(startOfNextLocalDay(noon) - startOfLocalDay(noon)).toBe(25 * HOUR_MS)
    })
  })

  it('a spring-forward day is 23 hours long (London)', () => {
    withTimeZone(LONDON, () => {
      const noon = new Date(2026, 2, 29, 12).getTime()
      expect(startOfNextLocalDay(noon) - startOfLocalDay(noon)).toBe(23 * HOUR_MS)
    })
  })

  it('a day whose midnight does not exist starts at its first real instant (São Paulo 2018)', () => {
    withTimeZone(SAO_PAULO, () => {
      const noon = new Date(2018, 10, 4, 12).getTime()
      const start = startOfLocalDay(noon)
      expect(new Date(start).getHours()).toBe(1)
      expect(localDayOrdinal(start)).toBe(20181104)
      // ...and "the start of the next day" from the day before lands on it too.
      expect(startOfNextLocalDay(new Date(2018, 10, 3, 12).getTime())).toBe(start)
    })
  })

  it('every instant of a 23-hour day maps to the same start and next start', () => {
    withTimeZone(NEW_YORK, () => {
      const start = new Date(2026, 2, 8).getTime()
      const next = new Date(2026, 2, 9).getTime()
      for (let t = start; t < next; t += 15 * 60 * 1000) {
        expect(startOfLocalDay(t)).toBe(start)
        expect(startOfNextLocalDay(t)).toBe(next)
      }
    })
  })
})

describe('addLocalDays across DST', () => {
  it('keeps the wall-clock time over a spring-forward night — 23 hours elapse, not 24', () => {
    withTimeZone(NEW_YORK, () => {
      const sat9am = new Date(2026, 2, 7, 9).getTime()
      const sun9am = addLocalDays(sat9am, 1)
      expect(new Date(sun9am).getHours()).toBe(9)
      expect(new Date(sun9am).getDate()).toBe(8)
      expect(sun9am - sat9am).toBe(23 * HOUR_MS)
    })
  })

  it('keeps the wall-clock time over a fall-back night — 25 hours elapse', () => {
    withTimeZone(NEW_YORK, () => {
      const sat9am = new Date(2026, 9, 31, 9).getTime()
      const sun9am = addLocalDays(sat9am, 1)
      expect(new Date(sun9am).getHours()).toBe(9)
      expect(sun9am - sat9am).toBe(25 * HOUR_MS)
    })
  })

  it('works backwards across a boundary too', () => {
    withTimeZone(LONDON, () => {
      const mon9am = new Date(2026, 2, 30, 9).getTime()
      const sat9am = addLocalDays(mon9am, -2)
      expect(new Date(sat9am).getDate()).toBe(28)
      expect(new Date(sat9am).getHours()).toBe(9)
    })
  })
})

describe('localDayKey', () => {
  it('is the local calendar date, zero-padded', () => {
    withTimeZone(KOLKATA, () => {
      expect(localDayKey(new Date(2026, 8, 1, 23, 59).getTime())).toBe('2026-09-01')
      // 03:00 IST is still the previous day in UTC — the key is the local one.
      expect(localDayKey(new Date(2026, 8, 11, 3).getTime())).toBe('2026-09-11')
    })
  })

  it('is one key for every instant of a DST day, including one with no midnight', () => {
    withTimeZone(NEW_YORK, () => {
      expect(localDayKey(new Date(2026, 2, 8, 0, 30).getTime())).toBe('2026-03-08')
      expect(localDayKey(new Date(2026, 2, 8, 23, 30).getTime())).toBe('2026-03-08')
    })
    withTimeZone(SAO_PAULO, () => {
      expect(localDayKey(startOfLocalDay(new Date(2018, 10, 4, 12).getTime()))).toBe('2018-11-04')
    })
  })
})

describe('atLocalTimeOf', () => {
  it("puts one day's wall-clock time on another day, across a DST boundary", () => {
    withTimeZone(NEW_YORK, () => {
      const fri6pm = new Date(2026, 2, 6, 18, 5).getTime()
      const moved = atLocalTimeOf(new Date(2026, 2, 8).getTime(), fri6pm)
      expect(moved).toBe(new Date(2026, 2, 8, 18, 5).getTime())
      // Two calendar days on, but 47 hours elapsed, not 48.
      expect(moved - fri6pm).toBe(47 * HOUR_MS)
    })
  })

  it('a time inside the skipped hour resolves forward on the same day, not onto another day', () => {
    withTimeZone(NEW_YORK, () => {
      const sat230am = new Date(2026, 2, 7, 2, 30).getTime()
      const moved = new Date(atLocalTimeOf(new Date(2026, 2, 8).getTime(), sat230am))
      expect(moved.getDate()).toBe(8)
      expect(moved.getHours()).toBe(3)
      expect(moved.getMinutes()).toBe(30)
    })
  })

  it('midnight stays midnight', () => {
    withTimeZone(KOLKATA, () => {
      const day = new Date(2026, 8, 20).getTime()
      expect(atLocalTimeOf(day, new Date(2026, 8, 11).getTime())).toBe(day)
    })
  })
})

describe('compareLocalDays', () => {
  it('two instants 22 hours apart on a 23-hour day are the same day', () => {
    withTimeZone(NEW_YORK, () => {
      const early = new Date(2026, 2, 8, 0, 30).getTime()
      const late = new Date(2026, 2, 8, 23, 30).getTime()
      expect(late - early).toBe(22 * HOUR_MS)
      expect(compareLocalDays(late, early)).toBe(0)
    })
  })

  it('two instants 40 minutes apart either side of midnight are different days', () => {
    withTimeZone(NEW_YORK, () => {
      const beforeMidnight = new Date(2026, 2, 8, 23, 30).getTime()
      const afterMidnight = new Date(2026, 2, 9, 0, 10).getTime()
      expect(compareLocalDays(afterMidnight, beforeMidnight)).toBeGreaterThan(0)
      expect(compareLocalDays(beforeMidnight, afterMidnight)).toBeLessThan(0)
    })
  })

  it('uses local days, not UTC days — the case epoch-ms division gets wrong (Kolkata)', () => {
    withTimeZone(KOLKATA, () => {
      const threeAm = new Date(2026, 8, 11, 3).getTime()
      const sevenAm = new Date(2026, 8, 11, 7).getTime()
      // 03:00 IST is 21:30 UTC the previous day: dividing by a day's worth
      // of milliseconds puts these two on different days.
      const DAY_MS = 24 * HOUR_MS
      expect(Math.floor(threeAm / DAY_MS)).not.toBe(Math.floor(sevenAm / DAY_MS))
      expect(compareLocalDays(threeAm, sevenAm)).toBe(0)
    })
  })

  it('orders across month and year boundaries', () => {
    withTimeZone(KOLKATA, () => {
      const dec31 = new Date(2026, 11, 31, 23).getTime()
      const jan1 = new Date(2027, 0, 1, 1).getTime()
      const jan31 = new Date(2027, 0, 31).getTime()
      const feb1 = new Date(2027, 1, 1).getTime()
      expect(compareLocalDays(jan1, dec31)).toBeGreaterThan(0)
      expect(compareLocalDays(feb1, jan31)).toBeGreaterThan(0)
    })
  })
})
