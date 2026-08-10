/// <reference lib="webworker" />
/**
 * Runs only inside the leader tab's dedicated Worker (see client.ts for why
 * it's a dedicated Worker and not a SharedWorker, and for the leader
 * election that keeps exactly one of these alive at a time). Owns the only
 * open connection to the OPFS-backed SQLite database and exposes it over
 * Comlink.
 */
import sqlite3InitModule from '@sqlite.org/sqlite-wasm'
import * as Comlink from 'comlink'
import { applyMigrations, type SqliteConnection, type SqliteStatement } from './migrate.js'
import {
  compareMaterializedTables,
  mutate,
  replayOps,
  selectAllOps,
  type MutateInput,
  type MutateResult,
  type ReplayComparisonResult,
  type TableName,
} from './ops.js'
import { createHlcClock, type HlcClock, type HlcState } from './hlc.js'

const DB_FILENAME = '/life-helper.sqlite3'
const VFS_POOL_NAME = 'life-helper-pool'

// opfs-sahpool pre-allocates and locks every file handle in the pool up
// front, and its own docs say it "does not support client-transparent
// concurrency." During leader handoff (client.ts) a newly-promoted tab can
// call this within milliseconds of the previous leader's tab closing, and
// the browser doesn't guarantee that tab's Worker/OPFS handles are fully
// torn down that fast. Retrying absorbs that transient window instead of
// failing the whole handoff.
async function retryAsync<T>(fn: () => Promise<T>, attempts: number, delayMs: number): Promise<T> {
  let lastError: unknown
  for (let attempt = 0; attempt < attempts; attempt++) {
    try {
      return await fn()
    } catch (error) {
      lastError = error
      if (attempt < attempts - 1) {
        await new Promise((resolve) => setTimeout(resolve, delayMs))
      }
    }
  }
  throw lastError
}

interface Oo1Stmt {
  bind(params: unknown[]): Oo1Stmt
  step(): boolean
  get(target: Record<string, unknown>): Record<string, unknown>
  finalize(): void
}

interface Oo1Db {
  exec(sql: string): void
  prepare(sql: string): Oo1Stmt
}

/** Adapts sqlite-wasm's oo1 API to the same SqliteConnection shape migrate.ts and ops.ts already use against node:sqlite in tests. */
class SqliteWasmConnection implements SqliteConnection {
  private readonly db: Oo1Db

  constructor(db: Oo1Db) {
    this.db = db
  }

  exec(sql: string): void {
    this.db.exec(sql)
  }

  prepare(sql: string): SqliteStatement {
    const db = this.db
    return {
      all(...params: unknown[]) {
        const stmt = db.prepare(sql)
        try {
          if (params.length > 0) stmt.bind(params)
          const rows: Record<string, unknown>[] = []
          while (stmt.step()) {
            rows.push(stmt.get(Object.create(null) as Record<string, unknown>))
          }
          return rows
        } finally {
          stmt.finalize()
        }
      },
      run(...params: unknown[]) {
        const stmt = db.prepare(sql)
        try {
          if (params.length > 0) stmt.bind(params)
          stmt.step()
          return undefined
        } finally {
          stmt.finalize()
        }
      },
    }
  }
}

function loadLocalState(db: SqliteConnection, key: string): string | undefined {
  const rows = db.prepare('SELECT value FROM _local_state WHERE key = ?').all(key)
  const row = rows[0] as { value: string } | undefined
  return row?.value
}

function saveLocalState(db: SqliteConnection, key: string, value: string): void {
  db.prepare(
    `INSERT INTO _local_state (key, value) VALUES (?, ?)
     ON CONFLICT(key) DO UPDATE SET value = excluded.value`,
  ).run(key, value)
}

/**
 * device_id and HLC state live in a table inside the same database file
 * rather than as separate raw OPFS files. The database file is already
 * durably persisted in OPFS via the sahpool VFS, so this still satisfies
 * "persisted in OPFS" (Part A3's own wording) without juggling a second
 * storage mechanism. See docs/phase_A3_db_layer.md.
 */
function getOrCreateDeviceId(db: SqliteConnection): string {
  const existing = loadLocalState(db, 'device_id')
  if (existing) return existing
  const id = crypto.randomUUID()
  saveLocalState(db, 'device_id', id)
  return id
}

function createPersistedHlcClock(db: SqliteConnection, deviceId: string): HlcClock {
  return createHlcClock(deviceId, {
    load: () => {
      const raw = loadLocalState(db, 'hlc_state')
      return raw ? (JSON.parse(raw) as HlcState) : undefined
    },
    save: (state) => {
      saveLocalState(db, 'hlc_state', JSON.stringify(state))
    },
  })
}

type ChangeListener = (tables: TableName[]) => void

export class WorkerApiImpl {
  private db?: SqliteConnection
  private sqlite3?: Awaited<ReturnType<typeof sqlite3InitModule>>
  private deviceId = ''
  private clock?: HlcClock
  private readonly listeners = new Map<string, ChangeListener>()

  async init(): Promise<{ deviceId: string }> {
    const sqlite3 = await sqlite3InitModule()
    this.sqlite3 = sqlite3
    const poolUtil = await retryAsync(
      () => sqlite3.installOpfsSAHPoolVfs({ name: VFS_POOL_NAME }),
      8,
      250,
    )
    const oo1Db = new poolUtil.OpfsSAHPoolDb(DB_FILENAME) as unknown as Oo1Db
    const db = new SqliteWasmConnection(oo1Db)
    this.db = db

    applyMigrations(db)
    db.exec('CREATE TABLE IF NOT EXISTS _local_state (key TEXT PRIMARY KEY, value TEXT NOT NULL)')

    this.deviceId = getOrCreateDeviceId(db)
    this.clock = createPersistedHlcClock(db, this.deviceId)

    return { deviceId: this.deviceId }
  }

  mutate(input: MutateInput): MutateResult {
    if (!this.db || !this.clock) throw new Error('WorkerApiImpl.mutate() called before init()')
    const result = mutate(this.db, input, this.deviceId, this.clock)
    if (result.touchedTables.size > 0) {
      const tables = [...result.touchedTables]
      for (const listener of this.listeners.values()) listener(tables)
    }
    return result
  }

  query(sql: string, params: unknown[]): Record<string, unknown>[] {
    if (!this.db) throw new Error('WorkerApiImpl.query() called before init()')
    return this.db.prepare(sql).all(...params)
  }

  getDeviceId(): string {
    return this.deviceId
  }

  /**
   * Part B4's capture gate: "the ops replay test passes with real captured
   * data, not fixtures." Builds a fresh in-memory database, replays this
   * device's actual `ops` log into it, and compares every materialized
   * table against the live OPFS-backed one. Nothing here leaves the
   * device or the browser's own memory — the in-memory database is
   * discarded when this call returns (Decision 8's privacy boundary is
   * about network egress, not local computation, but there's no reason to
   * touch that line even so).
   */
  verifyReplay(): ReplayComparisonResult {
    if (!this.db) throw new Error('WorkerApiImpl.verifyReplay() called before init()')
    if (!this.sqlite3) throw new Error('WorkerApiImpl.verifyReplay() called before init()')

    const ops = selectAllOps(this.db)
    const replayedOo1 = new this.sqlite3.oo1.DB({ filename: ':memory:' }) as unknown as Oo1Db
    const replayedDb = new SqliteWasmConnection(replayedOo1)
    applyMigrations(replayedDb)
    replayOps(replayedDb, ops)

    return compareMaterializedTables(this.db, replayedDb)
  }

  /** Returns a subscription id; unsubscribe with offChange(id). */
  onChange(listener: ChangeListener): string {
    const id = crypto.randomUUID()
    this.listeners.set(id, listener)
    return id
  }

  offChange(id: string): void {
    this.listeners.delete(id)
  }
}

Comlink.expose(new WorkerApiImpl())
