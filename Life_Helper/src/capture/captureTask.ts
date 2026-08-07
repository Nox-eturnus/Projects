/**
 * Part B1's write path: raw capture text becomes one `items` row
 * (`kind='task'`, `status='inbox'`) plus its `task_fields` side table row,
 * written in a single mutate() call so the two are atomic (Decision 3 —
 * capture is one write, never two round trips the user could half-see).
 *
 * Pure aside from the injected `mutate`/`generateId`/`now`, so it's unit
 * tested without a real dbClient (which needs a Worker + OPFS, only
 * available in a real browser — see e2e/capture.spec.ts for that side).
 */
import { generateItemId } from '../db/id.js'
import type { MutateInput, MutateResult } from '../db/ops.js'

export interface CaptureTaskDeps {
  readonly mutate: (input: MutateInput) => Promise<MutateResult>
  readonly generateId?: () => string
  readonly now?: () => number
}

/**
 * Returns the new item's id, or null if `rawText` was blank (capture's only
 * required field is the raw text itself — nothing is written for empty
 * input).
 */
export async function captureTask(rawText: string, deps: CaptureTaskDeps): Promise<string | null> {
  const title = rawText.trim()
  if (title.length === 0) return null

  const generateId = deps.generateId ?? generateItemId
  const now = deps.now ?? Date.now
  const id = generateId()
  const timestamp = now()

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
        fields: {},
      },
    ],
  })

  return id
}
