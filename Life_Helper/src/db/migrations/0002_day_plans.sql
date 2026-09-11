-- Migration 0002: per-day plan state for Part C2 — Today's top 3 and the
-- evening shutdown ritual. See docs/phase_C2_today_shutdown.md for why this
-- is a table of its own rather than more columns on task_fields.

CREATE TABLE day_plans (
  day TEXT PRIMARY KEY,
  top1_id TEXT,
  top2_id TEXT,
  top3_id TEXT,
  committed_at INTEGER,
  committed_via TEXT CHECK (committed_via IN ('shutdown', 'proposal')),
  shutdown_completed_at INTEGER,
  hlc TEXT NOT NULL,
  origin_device TEXT NOT NULL
);
