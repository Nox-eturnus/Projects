import { useCallback, useEffect, useState } from 'react'
import {
  DEFAULT_SHUTDOWN_TIME,
  isValidShutdownTime,
  shutdownReminderAt,
} from './shutdownReminder.js'

const STORAGE_KEY = 'life-helper-shutdown-time'

function readStoredTime(): string {
  // localStorage can be unavailable or throw (private browsing, storage
  // disabled) — the reminder still works at the default time.
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY)
    return stored !== null && isValidShutdownTime(stored) ? stored : DEFAULT_SHUTDOWN_TIME
  } catch {
    return DEFAULT_SHUTDOWN_TIME
  }
}

/**
 * The configured shutdown reminder time, `HH:MM`. Stored per device, like
 * the theme: it's a preference about when this device nudges you, and
 * Part H3's push registration is where it will reach the Worker.
 */
export function useShutdownTime(): [string, (next: string) => void] {
  const [time, setTime] = useState(readStoredTime)
  const update = useCallback((next: string) => {
    if (!isValidShutdownTime(next)) return
    setTime(next)
    try {
      window.localStorage.setItem(STORAGE_KEY, next)
    } catch {
      // Not persisted; the in-memory value still applies this session.
    }
  }, [])
  return [time, update]
}

/**
 * Whether today's reminder time has passed — and it flips to true at that
 * time on its own if the app is already open, rather than waiting for a
 * re-render. `dayStart` is today's first instant (it changes at midnight,
 * which re-arms this for the new day).
 */
export function useShutdownTimeReached(dayStart: number, time: string): boolean {
  const reminderAt = shutdownReminderAt(dayStart, time)
  const [now, setNow] = useState(Date.now)

  useEffect(() => {
    const timeout = setTimeout(
      () => {
        // max() so a timer that fires a hair early still counts as reached,
        // rather than leaving no further timer scheduled.
        setNow(Math.max(Date.now(), reminderAt))
      },
      Math.max(0, reminderAt - Date.now()),
    )
    return () => {
      clearTimeout(timeout)
    }
  }, [reminderAt])

  return now >= reminderAt
}
