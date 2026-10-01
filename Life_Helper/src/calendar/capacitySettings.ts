import { useLocalValue } from '../lib/localStore.js'
import { DEFAULT_CAPACITY_SETTINGS, isValidTime, type CapacitySettings } from './capacity.js'

export const CAPACITY_SETTINGS_KEY = 'life-helper-capacity-settings'

/** Each field falls back to its default independently, so one bad value doesn't reset the rest. */
export function parseCapacitySettings(value: unknown): CapacitySettings {
  const record =
    typeof value === 'object' && value !== null ? (value as Record<string, unknown>) : {}
  const time = (field: unknown, fallback: string) =>
    typeof field === 'string' && isValidTime(field) ? field : fallback
  const buffer = record.bufferMinutes
  return {
    wakeStart: time(record.wakeStart, DEFAULT_CAPACITY_SETTINGS.wakeStart),
    wakeEnd: time(record.wakeEnd, DEFAULT_CAPACITY_SETTINGS.wakeEnd),
    bufferMinutes:
      typeof buffer === 'number' && Number.isFinite(buffer) && buffer >= 0 && buffer <= 12 * 60
        ? Math.round(buffer)
        : DEFAULT_CAPACITY_SETTINGS.bufferMinutes,
  }
}

/** Waking hours and buffer, per device (like the theme and the shutdown reminder time). */
export function useCapacitySettings(): [CapacitySettings, (next: CapacitySettings) => void] {
  const [settings, set] = useLocalValue(CAPACITY_SETTINGS_KEY, parseCapacitySettings)
  return [settings, set]
}
