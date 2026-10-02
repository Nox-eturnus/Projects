import { beforeEach, describe, expect, it } from 'vitest'
import { saveConnection } from '../calendar/calendarStore'
import { addLocalDays, localDayKey, startOfLocalDay } from '../scheduling/localDay'
import {
  CALENDAR_HEALTH_KEY,
  COLD_STARTS_KEY,
  deviceInfo,
  parseCalendarHealth,
  readCalendarHealth,
  readColdStarts,
  readOpenDays,
  recordCalendarRefresh,
  recordColdStart,
  recordConnectionSaved,
  recordOpen,
} from './gateLog'

const HOUR_MS = 60 * 60 * 1000
const TODAY = startOfLocalDay(new Date(2026, 9, 20, 12).getTime())

beforeEach(() => {
  window.localStorage.clear()
})

describe('calendar health', () => {
  it('counts each refresh by day, and tracks the first and latest success', () => {
    recordCalendarRefresh(null, TODAY + HOUR_MS)
    recordCalendarRefresh('offline', TODAY + 2 * HOUR_MS)
    recordCalendarRefresh('offline', TODAY + 3 * HOUR_MS)
    recordCalendarRefresh(null, addLocalDays(TODAY, 1) + HOUR_MS)

    const health = readCalendarHealth()
    expect(health.days[localDayKey(TODAY)]).toEqual({ ok: 1, problems: { offline: 2 } })
    expect(health.days[localDayKey(addLocalDays(TODAY, 1))]).toEqual({ ok: 1, problems: {} })
    expect(health.firstOkAt).toBe(TODAY + HOUR_MS)
    expect(health.lastOkAt).toBe(addLocalDays(TODAY, 1) + HOUR_MS)
  })

  it('a failure never moves the success span', () => {
    recordCalendarRefresh('reconnect_required', TODAY)
    expect(readCalendarHealth()).toMatchObject({ firstOkAt: null, lastOkAt: null })
  })

  it('saving the connection is intervention: it restarts the span', () => {
    recordCalendarRefresh(null, TODAY)
    recordConnectionSaved(TODAY + HOUR_MS)
    expect(readCalendarHealth()).toMatchObject({
      firstOkAt: null,
      lastOkAt: null,
      connectionSavedAt: TODAY + HOUR_MS,
    })
  })

  it('saveConnection() — Settings — records it', () => {
    recordCalendarRefresh(null, TODAY)
    saveConnection({ edgeUrl: 'https://x.example', deviceKey: 'k'.repeat(43) })
    expect(readCalendarHealth().firstOkAt).toBeNull()
    expect(readCalendarHealth().connectionSavedAt).not.toBeNull()
  })

  it('keeps only the newest 60 days', () => {
    for (let i = 0; i < 70; i++) recordCalendarRefresh(null, addLocalDays(TODAY, i))
    const days = Object.keys(readCalendarHealth().days).sort()
    expect(days).toHaveLength(60)
    expect(days[0]).toBe(localDayKey(addLocalDays(TODAY, 10)))
  })

  it('reads garbage as empty, never throws', () => {
    window.localStorage.setItem(
      CALENDAR_HEALTH_KEY,
      '{"days":{"nope":1,"2026-10-01":{"ok":-3,"problems":{"offline":"x","unauthorized":2}}}}',
    )
    expect(readCalendarHealth().days).toEqual({
      '2026-10-01': { ok: 0, problems: { unauthorized: 2 } },
    })
    expect(parseCalendarHealth('bad')).toMatchObject({ days: {}, firstOkAt: null })
  })
})

describe('cold starts and open days', () => {
  it('keeps the newest 30 cold starts and drops malformed ones', () => {
    window.localStorage.setItem(COLD_STARTS_KEY, '[{"at":1,"ms":"fast"}]')
    expect(readColdStarts()).toEqual([])
    for (let i = 0; i < 35; i++) recordColdStart({ at: i, ms: 500 + i, android: true })
    const samples = readColdStarts()
    expect(samples).toHaveLength(30)
    expect(samples[0].at).toBe(5)
  })

  it('records each day the app is opened, once', () => {
    recordOpen(TODAY + HOUR_MS)
    recordOpen(TODAY + 5 * HOUR_MS)
    recordOpen(addLocalDays(TODAY, 1) + HOUR_MS)
    expect(readOpenDays()).toEqual([localDayKey(TODAY), localDayKey(addLocalDays(TODAY, 1))])
  })
})

describe('deviceInfo', () => {
  it('tells an Android phone from a desktop', () => {
    expect(
      deviceInfo('Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 Chrome/131 Mobile'),
    ).toEqual({ android: true, mobile: true })
    expect(deviceInfo('Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131')).toEqual({
      android: false,
      mobile: false,
    })
    expect(deviceInfo('Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) Mobile')).toEqual({
      android: false,
      mobile: true,
    })
  })
})
