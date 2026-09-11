import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, renderHook } from '@testing-library/react'
import { withTimeZone } from '../test/timeZone'
import { useDeferralCutoff } from './useDeferralCutoff'

afterEach(() => {
  vi.useRealTimers()
})

describe('useDeferralCutoff', () => {
  it('is the start of tomorrow, and rolls over to the day after at local midnight', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date(2026, 8, 11, 23, 59))
    const { result } = renderHook(() => useDeferralCutoff())

    expect(result.current).toBe(new Date(2026, 8, 12).getTime())

    act(() => {
      vi.advanceTimersByTime(59_999)
    })
    expect(result.current).toBe(new Date(2026, 8, 12).getTime())

    act(() => {
      vi.advanceTimersByTime(1)
    })
    expect(result.current).toBe(new Date(2026, 8, 13).getTime())
  })

  it('keeps rolling over, one day at a time, across a spring-forward night', () => {
    withTimeZone('America/New_York', () => {
      vi.useFakeTimers()
      vi.setSystemTime(new Date(2026, 2, 7, 23, 0))
      const { result, unmount } = renderHook(() => useDeferralCutoff())

      expect(result.current).toBe(new Date(2026, 2, 8).getTime())
      act(() => {
        vi.advanceTimersByTime(60 * 60 * 1000) // → Sun 8 Mar 00:00
      })
      expect(result.current).toBe(new Date(2026, 2, 9).getTime())
      act(() => {
        vi.advanceTimersByTime(23 * 60 * 60 * 1000) // the 23-hour day → Mon 9 Mar 00:00
      })
      expect(result.current).toBe(new Date(2026, 2, 10).getTime())
      unmount()
    })
  })
})
