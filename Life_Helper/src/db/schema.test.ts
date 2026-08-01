/// <reference types="node" />
import { readFileSync, readdirSync } from 'node:fs'
import { DatabaseSync } from 'node:sqlite'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { applyMigrations, MIGRATIONS, type SqliteConnection } from './migrate'

const here = dirname(fileURLToPath(import.meta.url))
const repoRoot = join(here, '..', '..')

function createDb(): SqliteConnection {
  return new DatabaseSync(':memory:')
}

function freshMigratedDb(): SqliteConnection {
  const db = createDb()
  applyMigrations(db)
  return db
}

// Every real (non-bookkeeping, non-FTS-shadow) table in the schema.
// ops is excluded: it carries its own per-op device_id + hlc by
// construction (see docs/phase_A2_data_model.md) rather than the
// materialized-table hlc/origin_device pair.
const MATERIALIZED_TABLES = [
  'items',
  'links',
  'tags',
  'task_fields',
  'routine_fields',
  'container_fields',
  'person_fields',
  'note_fields',
]

describe('migrations: empty to head', () => {
  it('applies cleanly against a fresh database', () => {
    const db = createDb()
    expect(() => applyMigrations(db)).not.toThrow()
  })

  it('records every migration id in schema_migrations', () => {
    const db = freshMigratedDb()
    const rows = db.prepare('SELECT id FROM schema_migrations ORDER BY id').all()
    expect(rows.map((r) => r.id)).toEqual(MIGRATIONS.map((m) => m.id))
  })

  it('is idempotent: re-applying against an already-migrated database is a no-op', () => {
    const db = freshMigratedDb()
    const secondPass = applyMigrations(db)
    expect(secondPass).toEqual([])
  })

  it('creates every table named in the schema', () => {
    const db = freshMigratedDb()
    const rows = db
      .prepare("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name")
      .all()
    const names = new Set(rows.map((r) => r.name as string))
    for (const table of MATERIALIZED_TABLES) {
      expect(names.has(table)).toBe(true)
    }
  })
})

describe('every materialized table carries hlc and origin_device', () => {
  const db = freshMigratedDb()

  for (const table of MATERIALIZED_TABLES) {
    it(table, () => {
      const columns = db.prepare(`PRAGMA table_info(${table})`).all()
      const columnNames = columns.map((c) => c.name as string)
      expect(columnNames).toContain('hlc')
      expect(columnNames).toContain('origin_device')
    })
  }

  it('ops carries the per-op equivalent (hlc + device_id) instead', () => {
    const columns = db.prepare('PRAGMA table_info(ops)').all()
    const columnNames = columns.map((c) => c.name as string)
    expect(columnNames).toContain('hlc')
    expect(columnNames).toContain('device_id')
  })
})

describe('no autoincrement integer primary key anywhere', () => {
  const migrationFiles = readdirSync(join(here, 'migrations'))
    .filter((f) => f.endsWith('.sql'))
    .map((f) => join(here, 'migrations', f))
  const filesToScan = [...migrationFiles, join(here, 'schema.sql')]

  for (const file of filesToScan) {
    it(file.split(/[\\/]/).pop() ?? file, () => {
      const text = readFileSync(file, 'utf8')
      expect(text).not.toMatch(/INTEGER\s+PRIMARY\s+KEY/i)
    })
  }
})

describe('no hard delete against items, links, or tags', () => {
  // This is a static guard for Decision 2 ("deletes are tombstones, never
  // DELETE FROM"). It scans real source, not this file's own detection
  // regex, which is why the file list below excludes schema.test.ts.
  const FORBIDDEN = /DELETE\s+FROM\s+(items|links|tags)\b/i

  function walk(dir: string): string[] {
    const entries = readdirSync(dir, { withFileTypes: true })
    let files: string[] = []
    for (const entry of entries) {
      const full = join(dir, entry.name)
      if (entry.isDirectory()) {
        files = files.concat(walk(full))
      } else if (/\.(ts|tsx|sql)$/.test(entry.name) && full !== fileURLToPath(import.meta.url)) {
        files.push(full)
      }
    }
    return files
  }

  const srcDir = join(repoRoot, 'src')
  const files = walk(srcDir)

  it('scanned at least the migration and runner files', () => {
    expect(files.length).toBeGreaterThan(0)
  })

  for (const file of files) {
    it(`clean: ${file.slice(srcDir.length + 1)}`, () => {
      const text = readFileSync(file, 'utf8')
      expect(text).not.toMatch(FORBIDDEN)
    })
  }
})

// Each migration starts with its own "-- Migration N: ..." header comment,
// which schema.sql intentionally replaces with a single generated-file
// header of its own. The drift check below compares statement bodies only.
function stripLeadingCommentBlock(sql: string): string {
  const lines = sql.split('\n')
  let i = 0
  while (i < lines.length && (lines[i].trim() === '' || lines[i].trim().startsWith('--'))) {
    i++
  }
  return lines.slice(i).join('\n').trim()
}

describe('schema.sql matches the concatenation of migrations', () => {
  it('does not drift from src/db/migrations/*.sql', () => {
    const schemaSql = readFileSync(join(here, 'schema.sql'), 'utf8')
    for (const migration of MIGRATIONS) {
      expect(schemaSql).toContain(stripLeadingCommentBlock(migration.sql))
    }
  })
})

describe('FTS5', () => {
  it('returns a hit for a body-text query', () => {
    const db = freshMigratedDb()
    db.prepare(
      `INSERT INTO items (id, kind, title, body, created_at, updated_at, hlc, origin_device)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
    ).run(
      '0199a000-0000-7000-8000-000000000001',
      'note',
      'Reading list',
      'a note about sourdough starters',
      1,
      1,
      'hlc-1',
      'device-1',
    )

    const hits = db.prepare('SELECT rowid FROM items_fts WHERE items_fts MATCH ?').all('sourdough')

    expect(hits.length).toBe(1)
  })

  it('stays consistent after an update and a delete', () => {
    const db = freshMigratedDb()
    db.prepare(
      `INSERT INTO items (id, kind, title, body, created_at, updated_at, hlc, origin_device)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
    ).run(
      '0199a000-0000-7000-8000-000000000002',
      'task',
      'Buy milk',
      null,
      1,
      1,
      'hlc-1',
      'device-1',
    )

    db.prepare('UPDATE items SET title = ?, updated_at = ? WHERE id = ?').run(
      'Buy oat milk',
      2,
      '0199a000-0000-7000-8000-000000000002',
    )
    expect(
      db.prepare('SELECT rowid FROM items_fts WHERE items_fts MATCH ?').all('oat').length,
    ).toBe(1)

    db.prepare('DELETE FROM items WHERE id = ?').run('0199a000-0000-7000-8000-000000000002')
    expect(
      db.prepare('SELECT rowid FROM items_fts WHERE items_fts MATCH ?').all('oat').length,
    ).toBe(0)
  })
})

describe('fixture round trip: one row of every kind', () => {
  it('round-trips task, note, person, project, retainer, and routine', () => {
    const db = freshMigratedDb()
    const now = 1_700_000_000_000

    function insertItem(id: string, kind: string, title: string) {
      db.prepare(
        `INSERT INTO items (id, kind, title, created_at, updated_at, hlc, origin_device)
         VALUES (?, ?, ?, ?, ?, ?, ?)`,
      ).run(id, kind, title, now, now, `hlc-${id}`, 'device-fixture')
    }

    insertItem('task-1', 'task', 'Ship Part A2')
    db.prepare(
      `INSERT INTO task_fields (item_id, due_at, scheduled_for, touch_count, someday, hlc, origin_device)
       VALUES (?, ?, ?, ?, ?, ?, ?)`,
    ).run('task-1', now, now, 0, 0, 'hlc-task-1', 'device-fixture')

    insertItem('note-1', 'note', 'Idea: paper-textured UI')
    db.prepare(
      `INSERT INTO note_fields (item_id, note_kind, resurface_count, hlc, origin_device)
       VALUES (?, ?, ?, ?, ?)`,
    ).run('note-1', 'idea', 0, 'hlc-note-1', 'device-fixture')

    insertItem('person-1', 'person', 'Rahul')
    db.prepare(
      `INSERT INTO person_fields (item_id, cadence_days, hlc, origin_device)
       VALUES (?, ?, ?, ?)`,
    ).run('person-1', 30, 'hlc-person-1', 'device-fixture')

    insertItem('project-1', 'project', 'Life Helper')
    db.prepare(
      `INSERT INTO container_fields (item_id, container_kind, definition_of_done, hlc, origin_device)
       VALUES (?, ?, ?, ?, ?)`,
    ).run('project-1', 'project', 'Phase A shipped', 'hlc-project-1', 'device-fixture')

    insertItem('retainer-1', 'retainer', 'Acme retainer')
    db.prepare(
      `INSERT INTO container_fields (item_id, container_kind, budget_hours, budget_scope, hlc, origin_device)
       VALUES (?, ?, ?, ?, ?, ?)`,
    ).run('retainer-1', 'retainer', 10, 'hours', 'hlc-retainer-1', 'device-fixture')

    insertItem('routine-1', 'routine', 'Morning pages')
    db.prepare(
      `INSERT INTO routine_fields (item_id, cadence, time_block, hlc, origin_device)
       VALUES (?, ?, ?, ?, ?)`,
    ).run('routine-1', 'daily', 'morning', 'hlc-routine-1', 'device-fixture')

    db.prepare(
      `INSERT INTO links (from_id, to_id, rel, created_at, hlc, origin_device)
       VALUES (?, ?, ?, ?, ?, ?)`,
    ).run('task-1', 'project-1', 'belongs_to', now, 'hlc-link-1', 'device-fixture')

    db.prepare(
      `INSERT INTO tags (item_id, tag, created_at, hlc, origin_device)
       VALUES (?, ?, ?, ?, ?)`,
    ).run('task-1', 'urgent', now, 'hlc-tag-1', 'device-fixture')

    const items = db.prepare('SELECT id, kind, title FROM items ORDER BY id').all()
    expect(items).toEqual([
      { id: 'note-1', kind: 'note', title: 'Idea: paper-textured UI' },
      { id: 'person-1', kind: 'person', title: 'Rahul' },
      { id: 'project-1', kind: 'project', title: 'Life Helper' },
      { id: 'retainer-1', kind: 'retainer', title: 'Acme retainer' },
      { id: 'routine-1', kind: 'routine', title: 'Morning pages' },
      { id: 'task-1', kind: 'task', title: 'Ship Part A2' },
    ])

    const link = db.prepare('SELECT from_id, to_id, rel FROM links WHERE from_id = ?').all('task-1')
    expect(link).toEqual([{ from_id: 'task-1', to_id: 'project-1', rel: 'belongs_to' }])

    const tag = db.prepare('SELECT tag FROM tags WHERE item_id = ?').all('task-1')
    expect(tag).toEqual([{ tag: 'urgent' }])

    const containerKinds = db
      .prepare('SELECT item_id, container_kind FROM container_fields ORDER BY item_id')
      .all()
    expect(containerKinds).toEqual([
      { item_id: 'project-1', container_kind: 'project' },
      { item_id: 'retainer-1', container_kind: 'retainer' },
    ])
  })
})

describe('replay determinism', () => {
  it('replaying migrations from empty reproduces the same schema twice', () => {
    const dbA = freshMigratedDb()
    const dbB = freshMigratedDb()

    const schemaOf = (db: SqliteConnection) =>
      db
        .prepare(
          "SELECT type, name, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY name",
        )
        .all()

    expect(schemaOf(dbA)).toEqual(schemaOf(dbB))
  })
})
