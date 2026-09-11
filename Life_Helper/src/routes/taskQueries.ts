/**
 * The SQL behind every route that lists tasks, kept out of the component
 * files so schedule.test.ts can run each one against a real node:sqlite
 * database — not just assert on the string — to prove Part C1's "deferred
 * items are absent from every view until their date."
 *
 * Every query here binds `deferralCutoff(now)` (see useDeferralCutoff())
 * as its first parameter, for NOT_DEFERRED_SQL's placeholder.
 */
import { NOT_DEFERRED_SQL } from '../scheduling/schedule.js'

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

export const RECENT_CAPTURES_SQL = `
  SELECT items.id, items.title, items.created_at FROM items
  LEFT JOIN task_fields ON task_fields.item_id = items.id
  WHERE items.kind = 'task' AND items.status = 'inbox' AND items.deleted_at IS NULL
    AND ${NOT_DEFERRED_SQL}
  ORDER BY items.created_at DESC
  LIMIT 5
`
