import { describe, expect, it } from 'vitest'
import { compareHlc, createHlcClock, formatHlc, type HlcState, parseHlc, tick } from './hlc'

function memoryStore(initial?: HlcState) {
  let state = initial
  return {
    load: () => state,
    save: (next: HlcState) => {
      state = next
    },
  }
}

describe('formatHlc / parseHlc', () => {
  it('round-trips', () => {
    const state: HlcState = { physical: 1_700_000_000_000, logical: 42, deviceId: 'dev-1' }
    expect(parseHlc(formatHlc(state))).toEqual(state)
  })

  it('rejects negative fields', () => {
    expect(() => formatHlc({ physical: -1, logical: 0, deviceId: 'd' })).toThrow()
  })
})

describe('compareHlc', () => {
  it('orders by physical time first', () => {
    const a = formatHlc({ physical: 100, logical: 5, deviceId: 'z' })
    const b = formatHlc({ physical: 101, logical: 0, deviceId: 'a' })
    expect(compareHlc(a, b)).toBeLessThan(0)
  })

  it('orders by logical counter when physical ties', () => {
    const a = formatHlc({ physical: 100, logical: 1, deviceId: 'z' })
    const b = formatHlc({ physical: 100, logical: 2, deviceId: 'a' })
    expect(compareHlc(a, b)).toBeLessThan(0)
  })

  it('uses deviceId as the final tiebreaker', () => {
    const a = formatHlc({ physical: 100, logical: 1, deviceId: 'device-a' })
    const b = formatHlc({ physical: 100, logical: 1, deviceId: 'device-b' })
    expect(compareHlc(a, b)).toBeLessThan(0)
  })
})

describe('tick', () => {
  it('advances physical time and resets logical when the wall clock moves forward', () => {
    const prev: HlcState = { physical: 100, logical: 3, deviceId: 'd' }
    const next = tick(prev, 200)
    expect(next).toEqual({ physical: 200, logical: 0, deviceId: 'd' })
  })

  it('increments the logical counter when the wall clock has not moved', () => {
    const prev: HlcState = { physical: 100, logical: 3, deviceId: 'd' }
    const next = tick(prev, 100)
    expect(next).toEqual({ physical: 100, logical: 4, deviceId: 'd' })
  })

  it('increments the logical counter when the wall clock moves backwards', () => {
    const prev: HlcState = { physical: 100, logical: 3, deviceId: 'd' }
    const next = tick(prev, 50)
    expect(next).toEqual({ physical: 100, logical: 4, deviceId: 'd' })
  })
})

describe('createHlcClock', () => {
  it('produces a strictly increasing sequence of formatted timestamps', () => {
    const clock = createHlcClock('dev-1', memoryStore())
    const stamps = [clock.next(1_000), clock.next(1_000), clock.next(1_001)]
    expect(stamps[0]).not.toEqual(stamps[1])
    expect(compareHlc(stamps[0], stamps[1])).toBeLessThan(0)
    expect(compareHlc(stamps[1], stamps[2])).toBeLessThan(0)
  })

  it('never goes backwards across a reload, even if the wall clock regresses', () => {
    const store = memoryStore()

    const beforeReload = createHlcClock('dev-1', store)
    const lastBeforeReload = beforeReload.next(5_000)

    // Simulate a reload: a fresh clock instance backed by the same
    // persisted store, with the wall clock reporting an EARLIER time than
    // what was already persisted (a real scenario: NTP correction, a
    // suspended laptop waking up, a buggy system clock).
    const afterReload = createHlcClock('dev-1', store)
    const firstAfterReload = afterReload.next(1_000)

    expect(compareHlc(firstAfterReload, lastBeforeReload)).toBeGreaterThan(0)
  })

  it('peek() reflects the current state without advancing it', () => {
    const clock = createHlcClock('dev-1', memoryStore())
    const stamped = clock.next(1_000)
    expect(clock.peek()).toBe(stamped)
    expect(clock.peek()).toBe(stamped)
  })

  it('resumes from persisted state rather than restarting at zero', () => {
    const store = memoryStore()
    createHlcClock('dev-1', store).next(9_000)

    const resumed = createHlcClock('dev-1', store)
    expect(parseHlc(resumed.peek()).physical).toBe(9_000)
  })
})
