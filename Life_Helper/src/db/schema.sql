-- GENERATED SNAPSHOT — do not hand-edit.
--
-- This is the head schema: the exact concatenation of every file in
-- src/db/migrations/, in filename order, as of the migration listed below.
-- It exists so a human (or another tool) can read "what does the database
-- look like today" without mentally replaying the migration chain.
--
-- The migrations directory is the actual source of truth applied at
-- runtime (see src/db/migrate.ts). This file is checked in
-- src/db/schema.test.ts to never drift from it: edit the migrations, not
-- this file, and regenerate.
--
-- Head migration: 0001_init

CREATE TABLE items (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL CHECK (kind IN ('task', 'note', 'person', 'project', 'retainer', 'routine')),
  title TEXT NOT NULL,
  body TEXT,
  status TEXT,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  deleted_at INTEGER,
  hlc TEXT NOT NULL,
  origin_device TEXT NOT NULL
);

CREATE INDEX idx_items_kind ON items(kind);
CREATE INDEX idx_items_deleted_at ON items(deleted_at);

CREATE TABLE links (
  from_id TEXT NOT NULL,
  to_id TEXT NOT NULL,
  rel TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  deleted_at INTEGER,
  hlc TEXT NOT NULL,
  origin_device TEXT NOT NULL,
  PRIMARY KEY (from_id, to_id, rel)
);

CREATE INDEX idx_links_from ON links(from_id);
CREATE INDEX idx_links_to ON links(to_id);

CREATE TABLE tags (
  item_id TEXT NOT NULL,
  tag TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  deleted_at INTEGER,
  hlc TEXT NOT NULL,
  origin_device TEXT NOT NULL,
  PRIMARY KEY (item_id, tag)
);

CREATE INDEX idx_tags_item ON tags(item_id);

CREATE TABLE task_fields (
  item_id TEXT PRIMARY KEY,
  due_at INTEGER,
  scheduled_for INTEGER,
  defer_until INTEGER,
  estimate_min INTEGER,
  touch_count INTEGER NOT NULL DEFAULT 0,
  last_touched_at INTEGER,
  someday INTEGER NOT NULL DEFAULT 0,
  completed_at INTEGER,
  energy TEXT,
  next_action TEXT,
  hlc TEXT NOT NULL,
  origin_device TEXT NOT NULL
);

CREATE INDEX idx_task_fields_due_at ON task_fields(due_at);
CREATE INDEX idx_task_fields_scheduled_for ON task_fields(scheduled_for);
CREATE INDEX idx_task_fields_someday ON task_fields(someday);

CREATE TABLE routine_fields (
  item_id TEXT PRIMARY KEY,
  cadence TEXT NOT NULL,
  time_block TEXT,
  grace_budget_per_month INTEGER NOT NULL DEFAULT 2,
  paused_until INTEGER,
  hlc TEXT NOT NULL,
  origin_device TEXT NOT NULL
);

CREATE TABLE container_fields (
  item_id TEXT PRIMARY KEY,
  container_kind TEXT NOT NULL CHECK (container_kind IN ('project', 'retainer')),
  definition_of_done TEXT,
  cycle_start INTEGER,
  cycle_end INTEGER,
  budget_hours REAL,
  budget_scope TEXT,
  hlc TEXT NOT NULL,
  origin_device TEXT NOT NULL
);

CREATE TABLE person_fields (
  item_id TEXT PRIMARY KEY,
  cadence_days INTEGER,
  last_contact_at INTEGER,
  next_contact_due INTEGER,
  hlc TEXT NOT NULL,
  origin_device TEXT NOT NULL
);

CREATE TABLE note_fields (
  item_id TEXT PRIMARY KEY,
  note_kind TEXT NOT NULL CHECK (note_kind IN ('journal', 'highlight', 'quote', 'idea')),
  source TEXT,
  resurface_after INTEGER,
  resurface_count INTEGER NOT NULL DEFAULT 0,
  hlc TEXT NOT NULL,
  origin_device TEXT NOT NULL
);

CREATE TABLE ops (
  op_id TEXT PRIMARY KEY,
  entity_id TEXT NOT NULL,
  entity_table TEXT NOT NULL,
  field TEXT NOT NULL,
  value TEXT,
  hlc TEXT NOT NULL,
  device_id TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  synced_at INTEGER
);

CREATE INDEX idx_ops_entity_id ON ops(entity_id);
CREATE INDEX idx_ops_synced_at ON ops(synced_at);

CREATE VIRTUAL TABLE items_fts USING fts5(
  title,
  body,
  content='items',
  content_rowid='rowid'
);

-- items_fts is an external-content FTS5 index (Part A2's own schema, not
-- Part A3's mutate() path) — these triggers keep it consistent with items
-- regardless of which write path touches the table.
CREATE TRIGGER items_ai AFTER INSERT ON items BEGIN
  INSERT INTO items_fts(rowid, title, body) VALUES (new.rowid, new.title, new.body);
END;

CREATE TRIGGER items_ad AFTER DELETE ON items BEGIN
  INSERT INTO items_fts(items_fts, rowid, title, body) VALUES ('delete', old.rowid, old.title, old.body);
END;

CREATE TRIGGER items_au AFTER UPDATE ON items BEGIN
  INSERT INTO items_fts(items_fts, rowid, title, body) VALUES ('delete', old.rowid, old.title, old.body);
  INSERT INTO items_fts(rowid, title, body) VALUES (new.rowid, new.title, new.body);
END;
