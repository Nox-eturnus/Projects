import { useCallback, useMemo, useSyncExternalStore } from 'react'

/**
 * Per-device JSON values in localStorage — preferences and caches that
 * deliberately stay off the synced database (see docs/phase_C3_calendar.md
 * for which, and why). Every access is guarded: localStorage can be
 * missing or throw (private browsing, storage disabled), and then values
 * just read as absent and writes are dropped, never crash the page.
 *
 * `useLocalValue` subscribes, so a Settings change shows up in any mounted
 * component reading the same key — in this tab (a custom event, since the
 * standard `storage` event only fires in *other* tabs) and in others.
 */

const CHANGE_EVENT = 'life-helper-local-store'

function readRaw(key: string): string | null {
  try {
    return window.localStorage.getItem(key)
  } catch {
    return null
  }
}

export function readLocal<T>(key: string, parse: (value: unknown) => T): T {
  const raw = readRaw(key)
  if (raw === null) return parse(undefined)
  try {
    return parse(JSON.parse(raw))
  } catch {
    return parse(undefined)
  }
}

export function writeLocal(key: string, value: unknown): void {
  try {
    if (value === undefined) window.localStorage.removeItem(key)
    else window.localStorage.setItem(key, JSON.stringify(value))
  } catch {
    // Not persisted; nothing else to do.
  }
  window.dispatchEvent(new CustomEvent(CHANGE_EVENT, { detail: key }))
}

function subscribe(onChange: () => void): () => void {
  window.addEventListener(CHANGE_EVENT, onChange)
  window.addEventListener('storage', onChange)
  return () => {
    window.removeEventListener(CHANGE_EVENT, onChange)
    window.removeEventListener('storage', onChange)
  }
}

/**
 * `parse` turns whatever is stored (possibly nothing, possibly garbage from
 * an older version) into a valid value — it's the one place a stored
 * value's shape is checked. Pass a stable function (module-level), since
 * it's a memo dependency.
 */
export function useLocalValue<T>(
  key: string,
  parse: (value: unknown) => T,
): [T, (next: T | undefined) => void] {
  // The raw string is the snapshot: a primitive, so React can compare it
  // and only re-render when the stored value actually changed.
  const raw = useSyncExternalStore(subscribe, () => readRaw(key))
  const value = useMemo(() => {
    if (raw === null) return parse(undefined)
    try {
      return parse(JSON.parse(raw))
    } catch {
      return parse(undefined)
    }
  }, [raw, parse])
  const set = useCallback(
    (next: T | undefined) => {
      writeLocal(key, next)
    },
    [key],
  )
  return [value, set]
}
