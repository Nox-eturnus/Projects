/**
 * The SQL behind every route that lists tasks, kept out of the component
 * files so schedule.test.ts can run each one against a real node:sqlite
 * database — not just assert on the string — to prove Part C1's "deferred
 * items are absent from every view until their date."
 *
 * Every task query here binds a deferral cutoff (see deferralCutoff() and
 * useDeferralCutoff()) as its first parameter, for NOT_DEFERRED_SQL's
 * placeholder.
 */
import { NOT_DEFERRED_SQL } from '../scheduling/schedule.js'

/**
 * A task "broken down" in Part C4 is archived: kept, linked from its
 * subtasks, but out of every list. Every query that lists open work
 * includes this (the inbox queries already list only `status = 'inbox'`).
 */
export const NOT_ARCHIVED_SQL = `COALESCE(items.status, '') <> 'archived'`

export const INBOX_SQL = `
  SELECT items.id, items.title, items.status, items.created_at,
         task_fields.due_at, task_fields.scheduled_for, task_fields.defer_until,
         COALESCE(task_fields.touch_count, 0) AS touch_count, task_fields.last_touched_at,
         task_fields.someday, task_fields.completed_at
  FROM items
  LEFT JOIN task_fields ON task_fields.item_id = items.id
  WHERE items.kind = 'task' AND items.status = 'inbox' AND items.deleted_at IS NULL
    AND ${NOT_DEFERRED_SQL}
  ORDER BY items.created_at DESC
`

/**
 * Every task Today or the shutdown could show for a day: open tasks, plus
 * tasks completed since `?2` (so a finished top 3 still shows as finished,
 * and the shutdown can review what got done). Someday tasks never appear
 * (Decision 4). Status isn't filtered: a task captured with a date is on
 * that day whether or not it has been triaged yet. Ranking and slotting
 * happen in JS — see proposal.ts and TodayRoute. Archived tasks (Part C4's
 * "break it down") never appear either.
 *
 * Params: [deferralCutoff(the day being shown), completed-since instant].
 */
export const DAY_TASKS_SQL = `
  SELECT items.id, items.title, items.status, items.created_at,
         task_fields.due_at, task_fields.scheduled_for, task_fields.defer_until,
         COALESCE(task_fields.touch_count, 0) AS touch_count, task_fields.last_touched_at,
         task_fields.completed_at, task_fields.estimate_min
  FROM items
  LEFT JOIN task_fields ON task_fields.item_id = items.id
  WHERE items.kind = 'task' AND items.deleted_at IS NULL
    AND COALESCE(task_fields.someday, 0) = 0
    AND ${NOT_ARCHIVED_SQL}
    AND ${NOT_DEFERRED_SQL}
    AND (task_fields.completed_at IS NULL OR task_fields.completed_at >= ?)
`

/**
 * Part C4's Revisit view: the same rows as DAY_TASKS_SQL, plus the
 * project a task is filed under, which "break it down" copies onto the
 * new steps. Which of these are slipping is decided in JS (findSlipping()),
 * the same way Today ranks its proposal. Completed tasks come along only
 * so "do it now" can rebuild a top 3 that already has a finished task in it.
 *
 * Params: [deferralCutoff(today), start of today].
 */
export const SLIPPING_SQL = `
  SELECT items.id, items.title, items.status, items.created_at,
         task_fields.due_at, task_fields.scheduled_for, task_fields.defer_until,
         COALESCE(task_fields.touch_count, 0) AS touch_count, task_fields.last_touched_at,
         task_fields.completed_at, task_fields.estimate_min,
         (SELECT links.to_id FROM links
          WHERE links.from_id = items.id AND links.rel = 'project' AND links.deleted_at IS NULL
          ORDER BY links.created_at DESC LIMIT 1) AS project_id
  FROM items
  LEFT JOIN task_fields ON task_fields.item_id = items.id
  WHERE items.kind = 'task' AND items.deleted_at IS NULL
    AND COALESCE(task_fields.someday, 0) = 0
    AND ${NOT_ARCHIVED_SQL}
    AND ${NOT_DEFERRED_SQL}
    AND (task_fields.completed_at IS NULL OR task_fields.completed_at >= ?)
`

/** `day_plans` rows for up to two days. Params: [day key, day key]. */
export const DAY_PLANS_SQL = `
  SELECT day, top1_id, top2_id, top3_id, committed_at, committed_via, shutdown_completed_at
  FROM day_plans
  WHERE day IN (?, ?)
`

/**
 * When the user last did anything — the newest op's timestamp. Decision 7's
 * "cold" state is measured from this. By insertion order (rowid), not
 * MAX(created_at): constant time however long the ops log grows.
 */
export const LAST_ACTIVITY_SQL = `
  SELECT created_at AS last_active_at FROM ops ORDER BY rowid DESC LIMIT 1
`

export const RECENT_CAPTURES_SQL = `
  SELECT items.id, items.title, items.created_at FROM items
  LEFT JOIN task_fields ON task_fields.item_id = items.id
  WHERE items.kind = 'task' AND items.status = 'inbox' AND items.deleted_at IS NULL
    AND ${NOT_DEFERRED_SQL}
  ORDER BY items.created_at DESC
  LIMIT 5
`
