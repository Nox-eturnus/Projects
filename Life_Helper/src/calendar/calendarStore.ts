/**
 * The calendar's two per-device values, both in localStorage:
 *
 * - **Connection** — where the edge Worker is and this device's key for
 *   it. The key is this app's own credential for its own Worker (Part
 *   D3's pairing replaces it); Google's tokens never reach the device.
 * - **Cache** — the last events fetched, and how the last attempt went,
 *   so Today renders from it offline and after a reload, with no request
 *   needed. Deliberately not in the synced database: it's Google's data,
 *   not the user's, every device fetches its own, and putting it through
 *   mutate() would write ops for every refresh and replicate them to
 *   every other device in Phase D for nothing.
 */
import { recordConnectionSaved } from '../gate/gateLog.js'
import type { CalendarEvent } from '../../edge/src/contract.js'
import { readLocal, writeLocal } from '../lib/localStore.js'

export const CONNECTION_KEY = 'life-helper-calendar-connection'
export const CACHE_KEY = 'life-helper-calendar-cache'

export interface CalendarConnection {
  readonly edgeUrl: string
  readonly deviceKey: string
}

/**
 * What stopped the last refresh — each one asks the user for something
 * different (see edge/src/contract.ts). `offline` covers every way the
 * request never got an answer at all.
 */
export type CalendarProblem =
  'offline' | 'unauthorized' | 'reconnect_required' | 'not_configured' | 'upstream_error'

export interface CalendarCache {
  readonly events: readonly CalendarEvent[]
  /** When these events were fetched from Google; null until the first success. */
  readonly fetchedAt: number | null
  /** The instant range the cached events cover. */
  readonly rangeStart: number
  readonly rangeEnd: number
  /** The last refresh attempt, successful or not — what the 15-minute throttle counts from. */
  readonly lastAttemptAt: number
  readonly problem: CalendarProblem | null
}

export const EMPTY_CACHE: CalendarCache = {
  events: [],
  fetchedAt: null,
  rangeStart: 0,
  rangeEnd: 0,
  lastAttemptAt: 0,
  problem: null,
}

const PROBLEMS: readonly CalendarProblem[] = [
  'offline',
  'unauthorized',
  'reconnect_required',
  'not_configured',
  'upstream_error',
]

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

/** Built-in default Worker URL, if the build set one (VITE_EDGE_URL). */
const DEFAULT_EDGE_URL = import.meta.env.VITE_EDGE_URL ?? ''

export function parseConnection(value: unknown): CalendarConnection {
  const record = isRecord(value) ? value : {}
  return {
    edgeUrl: typeof record.edgeUrl === 'string' ? record.edgeUrl : DEFAULT_EDGE_URL,
    deviceKey: typeof record.deviceKey === 'string' ? record.deviceKey : '',
  }
}

export function isConnected(connection: CalendarConnection): boolean {
  return connection.edgeUrl.trim().length > 0 && connection.deviceKey.trim().length > 0
}

function isEvent(value: unknown): value is CalendarEvent {
  if (!isRecord(value) || typeof value.id !== 'string' || typeof value.title !== 'string') {
    return false
  }
  if (typeof value.busy !== 'boolean') return false
  if (value.allDay === true) {
    return typeof value.startDate === 'string' && typeof value.endDate === 'string'
  }
  return value.allDay === false && typeof value.start === 'number' && typeof value.end === 'number'
}

/** Anything unreadable — an older format, a hand-edited value — is an empty cache, not a crash. */
export function parseCache(value: unknown): CalendarCache {
  if (!isRecord(value) || !Array.isArray(value.events)) return EMPTY_CACHE
  const number = (field: unknown, fallback: number) =>
    typeof field === 'number' && Number.isFinite(field) ? field : fallback
  return {
    events: value.events.filter(isEvent),
    fetchedAt: typeof value.fetchedAt === 'number' ? value.fetchedAt : null,
    rangeStart: number(value.rangeStart, 0),
    rangeEnd: number(value.rangeEnd, 0),
    lastAttemptAt: number(value.lastAttemptAt, 0),
    problem: PROBLEMS.find((problem) => problem === value.problem) ?? null,
  }
}

export function readCache(): CalendarCache {
  return readLocal(CACHE_KEY, parseCache)
}

export function writeCache(cache: CalendarCache): void {
  writeLocal(CACHE_KEY, cache)
}

/** Saving a different connection drops the cache: it belonged to the old one. */
export function saveConnection(connection: CalendarConnection | undefined): void {
  writeLocal(CONNECTION_KEY, connection)
  writeLocal(CACHE_KEY, undefined)
  // Part C6 counts this as manual intervention in the calendar's week.
  recordConnectionSaved(Date.now())
}
