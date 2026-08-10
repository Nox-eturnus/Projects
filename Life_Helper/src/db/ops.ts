/**
 * mutate() is the single write entry point (Decision 2, 3): every write
 * appends one `ops` row per changed field and updates the materialized
 * table, in one transaction. replayOps() is the inverse — it reconstructs
 * materialized tables from an `ops` log alone, with no other input, which
 * is what Decision 2's replay claim and Part D2's sync engine both depend
 * on.
 *
 * Deliberately generic over `SqliteConnection` (from migrate.ts) rather
 * than any specific SQLite binding, so this file is unit-tested against
 * node:sqlite (see ops.test.ts) and driven by @sqlite.org/sqlite-wasm
 * inside worker.ts with no changes.
 */
import type { SqliteConnection } from './migrate.js'
import type { HlcClock } from './hlc.js'

export type SqlValue = string | number | null

export type TableName =
  | 'items'
  | 'links'
  | 'tags'
  | 'task_fields'
  | 'routine_fields'
  | 'container_fields'
  | 'person_fields'
  | 'note_fields'

interface TableConfig {
  readonly primaryKey: readonly string[]
  /** NOT NULL columns without a DEFAULT, excluding the primary key itself. */
  readonly required: readonly string[]
}

const TABLES: Record<TableName, TableConfig> = {
  items: { primaryKey: ['id'], required: ['kind', 'title', 'created_at', 'updated_at'] },
  links: { primaryKey: ['from_id', 'to_id', 'rel'], required: ['created_at'] },
  tags: { primaryKey: ['item_id', 'tag'], required: ['created_at'] },
  task_fields: { primaryKey: ['item_id'], required: [] },
  routine_fields: { primaryKey: ['item_id'], required: ['cadence'] },
  container_fields: { primaryKey: ['item_id'], required: ['container_kind'] },
  person_fields: { primaryKey: ['item_id'], required: [] },
  note_fields: { primaryKey: ['item_id'], required: ['note_kind'] },
}

export interface Write {
  readonly table: TableName
  /** Primary key column(s) → value. Identifies the row; never diffed as a field. */
  readonly key: Readonly<Record<string, string>>
  /** Non-primary-key columns to set. Only columns that actually change produce an `ops` row. */
  readonly fields: Readonly<Record<string, SqlValue>>
}

export interface MutateInput {
  readonly writes: readonly Write[]
}

export interface MutateResult {
  readonly touchedTables: ReadonlySet<TableName>
  readonly opsInserted: number
}

export interface OpRow {
  readonly op_id: string
  readonly entity_id: string
  readonly entity_table: string
  readonly field: string
  readonly value: string | null
  readonly hlc: string
  readonly device_id: string
  readonly created_at: number
}

// A control character, not a printable one: tags.tag is free text and
// could otherwise collide with a plain space or punctuation separator.
const ENTITY_ID_SEPARATOR = '\u0000'

// Not a real column. See the comment at its use site in mutate().
const ROW_MARKER_FIELD = '__row__'

function primaryKeyWhereClause(pk: readonly string[]): string {
  return pk.map((col) => `${col} = ?`).join(' AND ')
}

function computeEntityId(key: Readonly<Record<string, string>>, pk: readonly string[]): string {
  return pk.map((col) => key[col]).join(ENTITY_ID_SEPARATOR)
}

function decodeEntityId(entityId: string, pk: readonly string[]): Record<string, string> {
  const parts = entityId.split(ENTITY_ID_SEPARATOR)
  if (parts.length !== pk.length) {
    throw new Error(
      `entity_id "${entityId}" does not decode to ${String(pk.length)} key column(s) (${pk.join(', ')})`,
    )
  }
  const key: Record<string, string> = {}
  pk.forEach((col, i) => {
    key[col] = parts[i]
  })
  return key
}

function selectRow(
  db: SqliteConnection,
  table: TableName,
  key: Readonly<Record<string, string>>,
): Record<string, unknown> | undefined {
  const pk = TABLES[table].primaryKey
  const rows = db
    .prepare(`SELECT * FROM ${table} WHERE ${primaryKeyWhereClause(pk)}`)
    .all(...pk.map((col) => key[col]))
  return rows[0]
}

function valuesEqual(current: unknown, next: SqlValue): boolean {
  if (typeof current === 'bigint') return current === BigInt(next as number)
  return current === next
}

function diffFields(
  existing: Record<string, unknown> | undefined,
  fields: Readonly<Record<string, SqlValue>>,
): Record<string, SqlValue> {
  const changed: Record<string, SqlValue> = {}
  for (const [column, value] of Object.entries(fields)) {
    if (!existing || !valuesEqual(existing[column], value)) {
      changed[column] = value
    }
  }
  return changed
}

function validateRequiredFieldsPresent(
  table: TableName,
  fields: Readonly<Record<string, SqlValue>>,
): void {
  const missing = TABLES[table].required.filter((col) => !(col in fields))
  if (missing.length > 0) {
    throw new Error(
      `mutate(): creating a new row in "${table}" is missing required column(s): ${missing.join(', ')}`,
    )
  }
}

function applyToMaterializedTable(
  db: SqliteConnection,
  table: TableName,
  key: Readonly<Record<string, string>>,
  fields: Readonly<Record<string, SqlValue>>,
  hlc: string,
  deviceId: string,
  isNew: boolean,
): void {
  const pk = TABLES[table].primaryKey
  const columns = Object.keys(fields)

  if (isNew) {
    const allColumns = [...pk, ...columns, 'hlc', 'origin_device']
    const placeholders = allColumns.map(() => '?').join(', ')
    const values = [
      ...pk.map((col) => key[col]),
      ...columns.map((col) => fields[col]),
      hlc,
      deviceId,
    ]
    db.prepare(`INSERT INTO ${table} (${allColumns.join(', ')}) VALUES (${placeholders})`).run(
      ...values,
    )
    return
  }

  const setClause = [...columns.map((col) => `${col} = ?`), 'hlc = ?', 'origin_device = ?'].join(
    ', ',
  )
  const values = [...columns.map((col) => fields[col]), hlc, deviceId, ...pk.map((col) => key[col])]
  db.prepare(`UPDATE ${table} SET ${setClause} WHERE ${primaryKeyWhereClause(pk)}`).run(...values)
}

function insertOpRow(
  db: SqliteConnection,
  args: {
    entityId: string
    entityTable: TableName
    field: string
    value: SqlValue
    hlc: string
    deviceId: string
  },
): void {
  db.prepare(
    `INSERT INTO ops (op_id, entity_id, entity_table, field, value, hlc, device_id, created_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
  ).run(
    crypto.randomUUID(),
    args.entityId,
    args.entityTable,
    args.field,
    JSON.stringify(args.value),
    args.hlc,
    args.deviceId,
    Date.now(),
  )
}

/**
 * Applies every write in `input` inside one transaction. Each write ticks
 * the clock once (Write granularity, not per-field, not per-call) — the
 * resulting hlc is what lets replayOps() regroup a stream of per-field ops
 * back into the atomic per-row writes that produced them.
 */
export function mutate(
  db: SqliteConnection,
  input: MutateInput,
  deviceId: string,
  clock: HlcClock,
): MutateResult {
  const touchedTables = new Set<TableName>()
  let opsInserted = 0

  db.exec('BEGIN')
  try {
    for (const write of input.writes) {
      const config = TABLES[write.table]
      const existing = selectRow(db, write.table, write.key)

      if (!existing) validateRequiredFieldsPresent(write.table, write.fields)

      const changed = diffFields(existing, write.fields)
      const changedEntries = Object.entries(changed)
      const isCreation = !existing
      if (changedEntries.length === 0 && !isCreation) continue

      const hlc = clock.next()
      const entityId = computeEntityId(write.key, config.primaryKey)

      // A creation with no changed fields still needs at least one op, or
      // replayOps() would never learn this row exists at all (e.g. a
      // task_fields row created with every column left at its SQL
      // DEFAULT). ROW_MARKER_FIELD isn't a real column — it's stripped
      // back out in replayOps() before the row is reconstructed.
      const opsToLog: (readonly [string, SqlValue])[] =
        changedEntries.length > 0 ? changedEntries : [[ROW_MARKER_FIELD, 1]]

      for (const [field, value] of opsToLog) {
        insertOpRow(db, {
          entityId,
          entityTable: write.table,
          field,
          value,
          hlc,
          deviceId,
        })
        opsInserted += 1
      }

      applyToMaterializedTable(db, write.table, write.key, write.fields, hlc, deviceId, !existing)
      touchedTables.add(write.table)
    }
    db.exec('COMMIT')
  } catch (error) {
    db.exec('ROLLBACK')
    throw error
  }

  return { touchedTables, opsInserted }
}

export function selectAllOps(db: SqliteConnection): OpRow[] {
  return db.prepare('SELECT * FROM ops ORDER BY rowid').all() as unknown as OpRow[]
}

const MATERIALIZED_TABLES: readonly TableName[] = [
  'items',
  'links',
  'tags',
  'task_fields',
  'routine_fields',
  'container_fields',
  'person_fields',
  'note_fields',
]

export interface TableComparison {
  readonly table: TableName
  readonly liveRowCount: number
  readonly replayedRowCount: number
  readonly matches: boolean
}

export interface ReplayComparisonResult {
  readonly ok: boolean
  readonly tables: readonly TableComparison[]
}

// bigint (some sqlite bindings return integer columns this way) doesn't
// survive JSON.stringify, so it's normalized to a string first — this is
// only ever used to build a comparison key, never persisted or displayed
// as the value itself.
function normalizeValue(value: unknown): unknown {
  return typeof value === 'bigint' ? value.toString() : value
}

function rowKey(row: Record<string, unknown>): string {
  return JSON.stringify(
    Object.keys(row)
      .sort()
      .map((column) => [column, normalizeValue(row[column])]),
  )
}

function rowsMatch(
  a: readonly Record<string, unknown>[],
  b: readonly Record<string, unknown>[],
): boolean {
  if (a.length !== b.length) return false
  for (let i = 0; i < a.length; i++) {
    if (rowKey(a[i]) !== rowKey(b[i])) return false
  }
  return true
}

/**
 * Decision 2's replay claim, checked against whatever is actually in `live`
 * — not a fixture. `replayed` is expected to be a database built by running
 * `applyMigrations()` then `replayOps(replayed, selectAllOps(live))` on a
 * fresh connection; this function only compares the two, so it works
 * equally well against a `node:sqlite` fixture pair (see ops.test.ts) or a
 * real device's OPFS-backed database and an in-memory replay of it (see
 * worker.ts's verifyReplay(), Part B4's capture gate).
 *
 * Compares every materialized table's rows, ordered by primary key so row
 * order can't itself cause a false mismatch, column-order-independent.
 */
export function compareMaterializedTables(
  live: SqliteConnection,
  replayed: SqliteConnection,
): ReplayComparisonResult {
  const tables = MATERIALIZED_TABLES.map((table): TableComparison => {
    const orderBy = TABLES[table].primaryKey.join(', ')
    const liveRows = live.prepare(`SELECT * FROM ${table} ORDER BY ${orderBy}`).all()
    const replayedRows = replayed.prepare(`SELECT * FROM ${table} ORDER BY ${orderBy}`).all()
    return {
      table,
      liveRowCount: liveRows.length,
      replayedRowCount: replayedRows.length,
      matches: rowsMatch(liveRows, replayedRows),
    }
  })
  return { ok: tables.every((t) => t.matches), tables }
}

/**
 * Reconstructs materialized tables from an `ops` log alone. Groups ops by
 * (entity_table, entity_id, hlc) to recover the atomic per-row writes that
 * produced them — every op in one Write shares the exact same hlc because
 * mutate() ticks the clock once per Write, so this grouping is exact, not
 * heuristic. Groups are applied in first-occurrence order.
 */
export function replayOps(db: SqliteConnection, ops: readonly OpRow[]): void {
  interface Group {
    table: TableName
    entityId: string
    hlc: string
    deviceId: string
    fields: Record<string, SqlValue>
  }

  const groups = new Map<string, Group>()
  const order: string[] = []

  for (const op of ops) {
    const groupKey = `${op.entity_table}${ENTITY_ID_SEPARATOR}${op.entity_id}${ENTITY_ID_SEPARATOR}${op.hlc}`
    let group = groups.get(groupKey)
    if (!group) {
      group = {
        table: op.entity_table as TableName,
        entityId: op.entity_id,
        hlc: op.hlc,
        deviceId: op.device_id,
        fields: {},
      }
      groups.set(groupKey, group)
      order.push(groupKey)
    }
    if (op.field !== ROW_MARKER_FIELD) {
      group.fields[op.field] = JSON.parse(op.value ?? 'null') as SqlValue
    }
  }

  db.exec('BEGIN')
  try {
    for (const groupKey of order) {
      const group = groups.get(groupKey)
      if (!group) continue
      const pk = TABLES[group.table].primaryKey
      const key = decodeEntityId(group.entityId, pk)
      const existing = selectRow(db, group.table, key)
      applyToMaterializedTable(
        db,
        group.table,
        key,
        group.fields,
        group.hlc,
        group.deviceId,
        !existing,
      )
    }
    db.exec('COMMIT')
  } catch (error) {
    db.exec('ROLLBACK')
    throw error
  }
}
