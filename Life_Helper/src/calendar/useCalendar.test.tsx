import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, renderHook, waitFor } from '@testing-library/react'
import type { EventsResponse } from '../../edge/src/contract.js'
import { CONNECTION_KEY, readCache, saveConnection } from './calendarStore'
import { useCalendar } from './useCalendar'

const CONNECTION = { edgeUrl: 'https://edge.example.workers.dev', deviceKey: 'k'.repeat(43) }
const MINUTE = 60_000

let fetchMock: ReturnType<typeof vi.fn<typeof fetch>>

function body(): EventsResponse {
  return { fetchedAt: Date.now(), events: [] }
}

/** Moves the clock only. Nothing else happens with time — which is the point. */
function advance(ms: number): void {
  vi.setSystemTime(Date.now() + ms)
}

beforeEach(() => {
  // Only Date is faked: real timers keep waitFor working, and the hook
  // under test is supposed to use none of them.
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date(2026, 8, 11, 9, 0))
  fetchMock = vi.fn<typeof fetch>(() =>
    Promise.resolve(new Response(JSON.stringify(body()), { status: 200 })),
  )
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('useCalendar: on focus, at most every 15 minutes, never on a timer', () => {
  it('does nothing at all until this device is connected', () => {
    renderHook(() => useCalendar())
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('refreshes once on open, then only on focus — and throttled', async () => {
    saveConnection(CONNECTION)
    const { rerender } = renderHook(() => useCalendar())
    await waitFor(() => {
      expect(readCache().fetchedAt).not.toBeNull()
    })
    expect(fetchMock).toHaveBeenCalledTimes(1)

    // Refocused five minutes later: inside the 15-minute window.
    act(() => {
      advance(5 * MINUTE)
      window.dispatchEvent(new Event('focus'))
    })
    expect(fetchMock).toHaveBeenCalledTimes(1)

    // Left open for two hours, re-rendering, never refocused: still one
    // request, and nothing was even scheduled to make another.
    const setIntervalSpy = vi.spyOn(globalThis, 'setInterval')
    const setTimeoutSpy = vi.spyOn(globalThis, 'setTimeout')
    act(() => {
      advance(120 * MINUTE)
      rerender()
    })
    expect(setIntervalSpy).not.toHaveBeenCalled()
    expect(setTimeoutSpy).not.toHaveBeenCalled()
    expect(fetchMock).toHaveBeenCalledTimes(1)
    vi.restoreAllMocks()

    // Refocused: now it's due.
    act(() => {
      window.dispatchEvent(new Event('focus'))
    })
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(2)
    })
  })

  it('becoming visible, or coming back online, counts as focus', async () => {
    saveConnection(CONNECTION)
    renderHook(() => useCalendar())
    await waitFor(() => {
      expect(readCache().fetchedAt).not.toBeNull()
    })
    act(() => {
      advance(20 * MINUTE)
      window.dispatchEvent(new Event('online'))
    })
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(2)
    })
  })

  it('refreshNow skips the throttle', async () => {
    saveConnection(CONNECTION)
    const { result } = renderHook(() => useCalendar())
    await waitFor(() => {
      expect(result.current.cache.fetchedAt).not.toBeNull()
      expect(result.current.refreshing).toBe(false)
    })
    act(() => {
      result.current.refreshNow()
    })
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(2)
    })
  })

  it('disconnecting drops the cache and stops asking', async () => {
    saveConnection(CONNECTION)
    const { result } = renderHook(() => useCalendar())
    await waitFor(() => {
      expect(result.current.cache.fetchedAt).not.toBeNull()
    })
    act(() => {
      saveConnection(undefined)
    })
    expect(result.current.connected).toBe(false)
    expect(result.current.cache.fetchedAt).toBeNull()
    expect(window.localStorage.getItem(CONNECTION_KEY)).toBeNull()
    act(() => {
      advance(30 * MINUTE)
      window.dispatchEvent(new Event('focus'))
    })
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })
})
