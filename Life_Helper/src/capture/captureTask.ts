/**
 * The write path: a resolved capture becomes one `items` row
 * (`kind='task'`, `status='inbox'`) plus its `task_fields` side table row,
 * written in a single mutate() call so the two are atomic (Decision 3 —
 * capture is one write, never two round trips the user could half-see).
 *
 * Takes already-resolved input rather than raw text — Part B2's parser
 * (`resolveCapture()`) is what turns raw text into `{title, scheduledFor,
 * estimateMin}`, and it has to run in the UI layer anyway (chip removal
 * needs to be reflected before commit), so there's no raw text left to
 * parse by the time this is called.
 *
 * Pure aside from the injected `mutate`/`generateId`/`now`, so it's unit
 * tested without a real dbClient (which needs a Worker + OPFS, only
 * available in a real browser — see e2e/capture.spec.ts for that side).
 */
import { generateItemId } from '../db/id.js'
import type { MutateInput, MutateResult, SqlValue } from '../db/ops.js'

export interface CaptureTaskInput {
  readonly title: string
  readonly scheduledFor?: number | null
  readonly estimateMin?: number | null
}

export interface CaptureTaskDeps {
  readonly mutate: (input: MutateInput) => Promise<MutateResult>
  readonly generateId?: () => string
  readonly now?: () => number
}

/**
 * Returns the new item's id, or null if `input.title` was blank (capture's
 * only required field is the title itself — nothing is written for empty
 * input, even if `scheduledFor`/`estimateMin` were somehow set).
 */
export async function captureTask(
  input: CaptureTaskInput,
  deps: CaptureTaskDeps,
): Promise<string | null> {
  const title = input.title.trim()
  if (title.length === 0) return null

  const generateId = deps.generateId ?? generateItemId
  const now = deps.now ?? Date.now
  const id = generateId()
  const timestamp = now()

  const taskFields: Record<string, SqlValue> = {}
  if (input.scheduledFor != null) taskFields.scheduled_for = input.scheduledFor
  if (input.estimateMin != null) taskFields.estimate_min = input.estimateMin

  await deps.mutate({
    writes: [
      {
        table: 'items',
        key: { id },
        fields: {
          kind: 'task',
          title,
          status: 'inbox',
          created_at: timestamp,
          updated_at: timestamp,
        },
      },
      {
        table: 'task_fields',
        key: { item_id: id },
        fields: taskFields,
      },
    ],
  })

  return id
}
