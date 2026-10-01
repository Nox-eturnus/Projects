import { useCallback, useEffect, useSyncExternalStore } from 'react'
import { useLocalValue } from '../lib/localStore.js'
import {
  CACHE_KEY,
  CONNECTION_KEY,
  isConnected,
  parseCache,
  parseConnection,
  readCache,
  writeCache,
  type CalendarCache,
  type CalendarConnection,
} from './calendarStore.js'
import { fetchEvents, nextCache, refreshRange, shouldRefresh } from './calendarSync.js'

// One refresh at a time across every mounted component (Today and Settings
// can both be asking), observable so "Refreshing…" reflects a request that
// is actually out — not every focus event the throttle turned away.
let inFlight: Promise<void> | null = null
const inFlightListeners = new Set<() => void>()

function setInFlight(next: Promise<void> | null): void {
  inFlight = next
  for (const listener of inFlightListeners) listener()
}

function subscribeInFlight(listener: () => void): () => void {
  inFlightListeners.add(listener)
  return () => {
    inFlightListeners.delete(listener)
  }
}

function refresh(connection: CalendarConnection, force: boolean): void {
  if (inFlight) return
  const now = Date.now()
  if (!shouldRefresh(readCache(), now, force)) return
  const range = refreshRange(now)
  setInFlight(
    fetchEvents(connection, range)
      .then((result) => {
        // Re-read: the connection may have changed while the request was
        // out, and saveConnection() cleared the cache — a late answer from
        // the old one mustn't resurrect it.
        writeCache(nextCache(readCache(), result, range, Date.now()))
      })
      .finally(() => {
        setInFlight(null)
      }),
  )
}

export interface CalendarState {
  readonly connection: CalendarConnection
  readonly connected: boolean
  readonly cache: CalendarCache
  readonly refreshing: boolean
  /** A user-initiated refresh: skips the 15-minute throttle. */
  readonly refreshNow: () => void
}

/**
 * The calendar, as the cache has it, kept fresh on Part C3's cadence: one
 * attempt when a view using it mounts, then again whenever the app regains
 * focus, becomes visible, or comes back online — each throttled to once per
 * 15 minutes. No interval, no background timer.
 */
export function useCalendar(): CalendarState {
  const [connection] = useLocalValue(CONNECTION_KEY, parseConnection)
  const [cache] = useLocalValue(CACHE_KEY, parseCache)
  const refreshing = useSyncExternalStore(subscribeInFlight, () => inFlight !== null)
  const connected = isConnected(connection)

  useEffect(() => {
    if (!connected) return
    refresh(connection, false)
    function onFocus(): void {
      refresh(connection, false)
    }
    function onVisibility(): void {
      if (document.visibilityState === 'visible') refresh(connection, false)
    }
    window.addEventListener('focus', onFocus)
    window.addEventListener('online', onFocus)
    document.addEventListener('visibilitychange', onVisibility)
    return () => {
      window.removeEventListener('focus', onFocus)
      window.removeEventListener('online', onFocus)
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [connected, connection])

  const refreshNow = useCallback(() => {
    if (connected) refresh(connection, true)
  }, [connected, connection])

  return { connection, connected, cache, refreshing, refreshNow }
}
