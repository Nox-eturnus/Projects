/// <reference types="vite/client" />
/**
 * Environment-agnostic migration runner. Deliberately has no dependency on
 * any particular SQLite binding: it is exercised in tests against
 * `node:sqlite` (see schema.test.ts) and is the same code Part A3 will
 * drive against `@sqlite.org/sqlite-wasm` in the browser worker — only the
 * `SqliteConnection` adapter changes between the two.
 *
 * `import.meta.glob` needs an explicit `vite/client` types reference here
 * because this file is also reached (via ops.ts) from tsconfig.e2e.json,
 * which — unlike tsconfig.app.json — doesn't list "vite/client" in its
 * `types` array.
 */

export interface SqliteStatement {
  all(...params: unknown[]): Record<string, unknown>[]
  run(...params: unknown[]): unknown
}

export interface SqliteConnection {
  exec(sql: string): void
  prepare(sql: string): SqliteStatement
}

export interface Migration {
  readonly id: string
  readonly sql: string
}

const migrationModules = import.meta.glob('./migrations/*.sql', {
  eager: true,
  query: '?raw',
  import: 'default',
})

function migrationIdFromPath(path: string): string {
  const fileName = path.split('/').pop()
  if (!fileName) {
    throw new Error(`Could not derive a migration id from path: ${path}`)
  }
  return fileName.replace(/\.sql$/, '')
}

export const MIGRATIONS: readonly Migration[] = Object.entries(migrationModules)
  .map(([path, sql]) => ({ id: migrationIdFromPath(path), sql }))
  .sort((a, b) => a.id.localeCompare(b.id))

const SCHEMA_MIGRATIONS_TABLE = `
  CREATE TABLE IF NOT EXISTS schema_migrations (
    id TEXT PRIMARY KEY,
    applied_at INTEGER NOT NULL
  )
`

/**
 * Applies every migration in `MIGRATIONS` not yet recorded in
 * `schema_migrations`, in order, each inside its own transaction. Returns
 * the ids that were newly applied (empty if the database was already at
 * head). Safe to call repeatedly — already-applied migrations are skipped.
 */
export function applyMigrations(db: SqliteConnection): string[] {
  db.exec(SCHEMA_MIGRATIONS_TABLE)

  const appliedRows = db.prepare('SELECT id FROM schema_migrations').all()
  const applied = new Set(appliedRows.map((row) => row.id as string))

  const newlyApplied: string[] = []
  for (const migration of MIGRATIONS) {
    if (applied.has(migration.id)) continue

    db.exec('BEGIN')
    try {
      db.exec(migration.sql)
      db.prepare('INSERT INTO schema_migrations (id, applied_at) VALUES (?, ?)').run(
        migration.id,
        Date.now(),
      )
      db.exec('COMMIT')
    } catch (error) {
      db.exec('ROLLBACK')
      throw error
    }
    newlyApplied.push(migration.id)
  }

  return newlyApplied
}
