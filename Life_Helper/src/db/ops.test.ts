/// <reference types="node" />
import { DatabaseSync } from 'node:sqlite'
import { describe, expect, it } from 'vitest'
import { applyMigrations, type SqliteConnection } from './migrate'
import { createHlcClock, type HlcState } from './hlc'
import { compareMaterializedTables, mutate, replayOps, selectAllOps, type MutateInput } from './ops'

function memoryStore() {
  let state: HlcState | undefined
  return {
    load: () => state,
    save: (next: HlcState) => {
      state = next
    },
  }
}

function freshDb(): SqliteConnection {
  const db = new DatabaseSync(':memory:')
  applyMigrations(db)
  return db
}

function clockFor(deviceId: string) {
  return createHlcClock(deviceId, memoryStore())
}

function tableRows(db: SqliteConnection, table: string) {
  return db.prepare(`SELECT * FROM ${table} ORDER BY rowid`).all()
}

describe('mutate: ops-per-changed-field', () => {
  it('produces exactly one ops row per changed field across multiple writes in one call', () => {
    const db = freshDb()
    const input: MutateInput = {
      writes: [
        {
          table: 'items',
          key: { id: 'task-1' },
          fields: { kind: 'task', title: 'Ship A3', created_at: 1, updated_at: 1 },
        },
        {
          table: 'task_fields',
          key: { item_id: 'task-1' },
          fields: { due_at: 100, touch_count: 0 },
        },
      ],
    }

    const result = mutate(db, input, 'device-1', clockFor('device-1'))

    // 4 fields on items + 2 fields on task_fields = 6
    expect(result.opsInserted).toBe(6)
    expect([...result.touchedTables].sort()).toEqual(['items', 'task_fields'])
    expect(selectAllOps(db)).toHaveLength(6)
  })

  it('a no-op write (values unchanged) produces zero ops rows and does not touch bookkeeping', () => {
    const db = freshDb()
    const clock = clockFor('device-1')
    const create: MutateInput = {
      writes: [
        {
          table: 'items',
          key: { id: 'task-1' },
          fields: { kind: 'task', title: 'Ship A3', created_at: 1, updated_at: 1 },
        },
      ],
    }
    mutate(db, create, 'device-1', clock)
    const opsAfterCreate = selectAllOps(db).length
    const hlcAfterCreate = (tableRows(db, 'items')[0] as { hlc: string }).hlc

    const noop: MutateInput = {
      writes: [
        { table: 'items', key: { id: 'task-1' }, fields: { title: 'Ship A3' } }, // identical value
      ],
    }
    const result = mutate(db, noop, 'device-1', clock)

    expect(result.opsInserted).toBe(0)
    expect(result.touchedTables.size).toBe(0)
    expect(selectAllOps(db)).toHaveLength(opsAfterCreate)
    expect((tableRows(db, 'items')[0] as { hlc: string }).hlc).toBe(hlcAfterCreate)
  })

  it('only the fields that actually changed produce ops rows on an update', () => {
    const db = freshDb()
    const clock = clockFor('device-1')
    mutate(
      db,
      {
        writes: [
          {
            table: 'items',
            key: { id: 'task-1' },
            fields: {
              kind: 'task',
              title: 'Original',
              status: 'inbox',
              created_at: 1,
              updated_at: 1,
            },
          },
        ],
      },
      'device-1',
      clock,
    )

    const result = mutate(
      db,
      {
        writes: [
          {
            table: 'items',
            key: { id: 'task-1' },
            fields: { title: 'Updated', status: 'inbox' }, // status unchanged, title changed
          },
        ],
      },
      'device-1',
      clock,
    )

    expect(result.opsInserted).toBe(1)
    const ops = selectAllOps(db)
    const lastOp = ops[ops.length - 1]
    expect(lastOp.field).toBe('title')
  })

  it('logs a row-marker op for a creation with zero non-key fields, so it stays replayable', () => {
    const db = freshDb()
    mutate(
      db,
      {
        writes: [
          {
            table: 'items',
            key: { id: 'task-1' },
            fields: { kind: 'task', title: 'T', created_at: 1, updated_at: 1 },
          },
          { table: 'task_fields', key: { item_id: 'task-1' }, fields: {} },
        ],
      },
      'device-1',
      clockFor('device-1'),
    )

    const row = tableRows(db, 'task_fields')[0] as { item_id: string; touch_count: number }
    expect(row.item_id).toBe('task-1')
    expect(row.touch_count).toBe(0) // SQL DEFAULT, never set as a field

    const ops = selectAllOps(db).filter((op) => op.entity_table === 'task_fields')
    expect(ops.length).toBeGreaterThan(0)
  })

  it('rejects creating a row without its required columns', () => {
    const db = freshDb()
    expect(() =>
      mutate(
        db,
        { writes: [{ table: 'items', key: { id: 'task-1' }, fields: { title: 'Missing kind' } }] },
        'device-1',
        clockFor('device-1'),
      ),
    ).toThrow(/missing required column/i)
  })

  it('rolls back the whole call if one write in it fails', () => {
    const db = freshDb()
    const clock = clockFor('device-1')
    expect(() =>
      mutate(
        db,
        {
          writes: [
            {
              table: 'items',
              key: { id: 'task-1' },
              fields: { kind: 'task', title: 'T', created_at: 1, updated_at: 1 },
            },
            { table: 'items', key: { id: 'task-2' }, fields: { title: 'Missing kind' } }, // fails validation
          ],
        },
        'device-1',
        clock,
      ),
    ).toThrow()
    expect(tableRows(db, 'items')).toHaveLength(0)
    expect(selectAllOps(db)).toHaveLength(0)
  })

  it('supports links and tags, whose primary key is composite', () => {
    const db = freshDb()
    const clock = clockFor('device-1')
    mutate(
      db,
      {
        writes: [
          {
            table: 'items',
            key: { id: 'task-1' },
            fields: { kind: 'task', title: 'T', created_at: 1, updated_at: 1 },
          },
          {
            table: 'items',
            key: { id: 'project-1' },
            fields: { kind: 'project', title: 'P', created_at: 1, updated_at: 1 },
          },
          {
            table: 'links',
            key: { from_id: 'task-1', to_id: 'project-1', rel: 'belongs_to' },
            fields: { created_at: 1 },
          },
          {
            table: 'tags',
            key: { item_id: 'task-1', tag: 'urgent priority' }, // contains a space, deliberately
            fields: { created_at: 1 },
          },
        ],
      },
      'device-1',
      clock,
    )

    expect(tableRows(db, 'links')).toHaveLength(1)
    const tagRow = tableRows(db, 'tags')[0] as { tag: string }
    expect(tagRow.tag).toBe('urgent priority')
  })
})

describe('replayOps', () => {
  it('reproduces the materialized tables byte-identically from an ops log alone', () => {
    const source = freshDb()
    const clock = clockFor('device-1')

    mutate(
      source,
      {
        writes: [
          {
            table: 'items',
            key: { id: 'task-1' },
            fields: {
              kind: 'task',
              title: 'Ship A3',
              status: 'inbox',
              created_at: 1,
              updated_at: 1,
            },
          },
          {
            table: 'task_fields',
            key: { item_id: 'task-1' },
            fields: { due_at: 100, touch_count: 0 },
          },
        ],
      },
      'device-1',
      clock,
    )
    // A later, separate write updating just one field.
    mutate(
      source,
      { writes: [{ table: 'items', key: { id: 'task-1' }, fields: { status: 'scheduled' } }] },
      'device-1',
      clock,
    )
    mutate(
      source,
      {
        writes: [
          {
            table: 'items',
            key: { id: 'project-1' },
            fields: { kind: 'project', title: 'Life Helper', created_at: 2, updated_at: 2 },
          },
          { table: 'task_fields', key: { item_id: 'task-1' }, fields: {} }, // no-op, already exists
          {
            table: 'links',
            key: { from_id: 'task-1', to_id: 'project-1', rel: 'belongs_to' },
            fields: { created_at: 3 },
          },
        ],
      },
      'device-1',
      clock,
    )

    const ops = selectAllOps(source)
    expect(ops.length).toBeGreaterThan(0)

    const target = freshDb() // migrations applied, zero data
    replayOps(target, ops)

    for (const table of [
      'items',
      'links',
      'tags',
      'task_fields',
      'routine_fields',
      'container_fields',
      'person_fields',
      'note_fields',
    ]) {
      expect(tableRows(target, table)).toEqual(tableRows(source, table))
    }
  })

  it('is order-independent per entity as long as groups are applied in first-occurrence order', () => {
    const source = freshDb()
    const clock = clockFor('device-1')
    mutate(
      source,
      {
        writes: [
          {
            table: 'items',
            key: { id: 'task-1' },
            fields: { kind: 'task', title: 'V1', created_at: 1, updated_at: 1 },
          },
        ],
      },
      'device-1',
      clock,
    )
    mutate(
      source,
      { writes: [{ table: 'items', key: { id: 'task-1' }, fields: { title: 'V2' } }] },
      'device-1',
      clock,
    )
    mutate(
      source,
      { writes: [{ table: 'items', key: { id: 'task-1' }, fields: { title: 'V3' } }] },
      'device-1',
      clock,
    )

    const target = freshDb()
    replayOps(target, selectAllOps(source))

    const row = tableRows(target, 'items')[0] as { title: string }
    expect(row.title).toBe('V3') // last write wins, in original op order
  })

  it('replaying the empty ops log against a fresh database is a no-op', () => {
    const target = freshDb()
    expect(() => {
      replayOps(target, [])
    }).not.toThrow()
    for (const table of ['items', 'links', 'tags', 'task_fields']) {
      expect(tableRows(target, table)).toEqual([])
    }
  })
})

describe('compareMaterializedTables', () => {
  it('reports ok when a replay reproduces the live database exactly', () => {
    const live = freshDb()
    const clock = clockFor('device-1')
    mutate(
      live,
      {
        writes: [
          {
            table: 'items',
            key: { id: 'task-1' },
            fields: { kind: 'task', title: 'Ship B4', created_at: 1, updated_at: 1 },
          },
          { table: 'task_fields', key: { item_id: 'task-1' }, fields: { due_at: 100 } },
        ],
      },
      'device-1',
      clock,
    )
    mutate(
      live,
      { writes: [{ table: 'items', key: { id: 'task-1' }, fields: { title: 'Ship B4 gate' } }] },
      'device-1',
      clock,
    )

    const replayed = freshDb()
    replayOps(replayed, selectAllOps(live))

    const result = compareMaterializedTables(live, replayed)
    expect(result.ok).toBe(true)
    expect(result.tables.every((t) => t.matches)).toBe(true)
    const itemsComparison = result.tables.find((t) => t.table === 'items')
    expect(itemsComparison).toMatchObject({ liveRowCount: 1, replayedRowCount: 1, matches: true })
  })

  it('reports which table diverges when the replay does not match', () => {
    const live = freshDb()
    const replayed = freshDb()
    const clock = clockFor('device-1')
    mutate(
      live,
      {
        writes: [
          {
            table: 'items',
            key: { id: 'task-1' },
            fields: { kind: 'task', title: 'Original', created_at: 1, updated_at: 1 },
          },
        ],
      },
      'device-1',
      clock,
    )
    // Simulate a divergence directly, rather than through replayOps, so
    // this test is about the comparison itself, not replay correctness
    // (which the "reproduces exactly" case above already covers).
    mutate(
      replayed,
      {
        writes: [
          {
            table: 'items',
            key: { id: 'task-1' },
            fields: { kind: 'task', title: 'Diverged', created_at: 1, updated_at: 1 },
          },
        ],
      },
      'device-1',
      clockFor('device-1'),
    )

    const result = compareMaterializedTables(live, replayed)
    expect(result.ok).toBe(false)
    const itemsComparison = result.tables.find((t) => t.table === 'items')
    expect(itemsComparison?.matches).toBe(false)
    expect(result.tables.filter((t) => t.table !== 'items').every((t) => t.matches)).toBe(true)
  })

  it('is order-independent: differently-ordered but equal rows still match', () => {
    const live = freshDb()
    const replayed = freshDb()
    // A fixed hlc for both writes in both databases — using two real
    // (Date.now()-based) clocks here would make the two databases' `hlc`
    // columns differ by however many milliseconds elapsed between the two
    // mutate() calls below, turning this into a flaky test of clock timing
    // rather than the row-ordering independence it's meant to check.
    const fixedClock = { next: () => '000000000000001:00000:device-1', peek: () => '' }
    for (const db of [live, replayed]) {
      mutate(
        db,
        {
          writes: [
            {
              table: 'items',
              key: { id: 'b' },
              fields: { kind: 'task', title: 'B', created_at: 2, updated_at: 2 },
            },
            {
              table: 'items',
              key: { id: 'a' },
              fields: { kind: 'task', title: 'A', created_at: 1, updated_at: 1 },
            },
          ],
        },
        'device-1',
        fixedClock,
      )
    }

    expect(compareMaterializedTables(live, replayed).ok).toBe(true)
  })
})
