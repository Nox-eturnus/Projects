-- Migration 0003: Part C5's amnesty. A sweep is a row of its own, so its
-- 24-hour undo survives a reload (and, from Phase D, reaches the other
-- devices); each task it moved to someday carries the sweep's id, so undo
-- restores exactly those tasks and no others. See docs/phase_C5_amnesty.md.

ALTER TABLE task_fields ADD COLUMN amnesty_sweep_id TEXT;

CREATE INDEX idx_task_fields_amnesty_sweep_id ON task_fields(amnesty_sweep_id);

CREATE TABLE amnesty_sweeps (
  id TEXT PRIMARY KEY,
  swept_at INTEGER NOT NULL,
  threshold_days INTEGER NOT NULL,
  item_count INTEGER NOT NULL,
  undone_at INTEGER,
  hlc TEXT NOT NULL,
  origin_device TEXT NOT NULL
);
