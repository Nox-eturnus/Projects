/**
 * Hybrid Logical Clock (Kulkarni et al.). Pure logic — no I/O of its own.
 * `createHlcClock` is handed a `HlcStore` (load/save) so the caller decides
 * where state is persisted; the worker will back it with a row in the same
 * SQLite database that already lives durably in OPFS (see
 * docs/phase_A3_db_layer.md), and tests back it with a plain in-memory Map.
 */

export interface HlcState {
  readonly physical: number
  readonly logical: number
  readonly deviceId: string
}

const PHYSICAL_WIDTH = 15 // digits — covers ms-since-epoch well past year 2286
const LOGICAL_WIDTH = 5 // digits — 99,999 ticks within the same millisecond

/**
 * Encodes state as a string that sorts correctly with plain `<`/string
 * comparison: fixed-width zero-padded physical, then logical, then
 * deviceId as the final tiebreaker.
 */
export function formatHlc(state: HlcState): string {
  if (state.physical < 0 || state.logical < 0) {
    throw new Error(`HLC fields must be non-negative: ${JSON.stringify(state)}`)
  }
  return `${state.physical.toString().padStart(PHYSICAL_WIDTH, '0')}:${state.logical
    .toString()
    .padStart(LOGICAL_WIDTH, '0')}:${state.deviceId}`
}

export function parseHlc(value: string): HlcState {
  const parts = value.split(':')
  if (parts.length < 3) {
    throw new Error(`Malformed HLC value: ${value}`)
  }
  const [physicalPart, logicalPart, ...deviceParts] = parts
  return {
    physical: Number(physicalPart),
    logical: Number(logicalPart),
    deviceId: deviceParts.join(':'),
  }
}

/** Formatted HLC strings compare correctly with plain string comparison. */
export function compareHlc(a: string, b: string): number {
  if (a === b) return 0
  return a < b ? -1 : 1
}

/**
 * Advances `prev` for one local event. Monotonic even if `wallNow` is at or
 * behind `prev.physical` (clock hasn't moved, or moved backwards) — the
 * logical counter absorbs that case instead of the tuple ever going
 * backwards.
 */
export function tick(prev: HlcState, wallNow: number = Date.now()): HlcState {
  const physical = Math.max(wallNow, prev.physical)
  const logical = physical === prev.physical ? prev.logical + 1 : 0
  return { physical, logical, deviceId: prev.deviceId }
}

export interface HlcStore {
  load(): HlcState | undefined
  save(state: HlcState): void
}

export interface HlcClock {
  /** Advances the clock for one local event and persists the new state. */
  next(wallNow?: number): string
  /** Returns the current state without advancing it. */
  peek(): string
}

export function createHlcClock(deviceId: string, store: HlcStore): HlcClock {
  let state: HlcState = store.load() ?? { physical: 0, logical: 0, deviceId }

  return {
    next(wallNow: number = Date.now()): string {
      state = tick(state, wallNow)
      store.save(state)
      return formatHlc(state)
    },
    peek(): string {
      return formatHlc(state)
    },
  }
}
