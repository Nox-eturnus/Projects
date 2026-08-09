/**
 * Part B3's triage logic: pure, synchronous. Each action produces a
 * forward `Write[]` and its exact inverse `undoWrites`, computed from a
 * snapshot of the item's current row — the toast's 10-second undo window
 * (Decision 7's "every action is undoable") is just "run `undoWrites`
 * through the same mutate() the forward action used," not bespoke
 * per-action revert code.
 *
 * Only the columns each action actually touches are ever read from or
 * written back to `TriageItem` — mutate() only logs a field as an op if it
 * differs from what's already there, so an undo write that happens to
 * match the current value again is a safe no-op, not a phantom op.
 */
import type { SqlValue, Write } from '../db/ops.js'

export interface TriageItem {
  readonly id: string
  readonly status: string | null
  readonly scheduledFor: number | null
  readonly someday: number
  readonly completedAt: number | null
}

export type TriageAction =
  | { readonly type: 'scheduleToday' }
  | { readonly type: 'scheduleDate'; readonly date: number }
  | { readonly type: 'fileToProject'; readonly projectId: string; readonly projectTitle: string }
  | { readonly type: 'convertToNote' }
  | { readonly type: 'convertToRoutine' }
  | { readonly type: 'someday' }
  | { readonly type: 'done' }
  | { readonly type: 'delete' }

export interface TriagePlan {
  readonly label: string
  readonly writes: readonly Write[]
  readonly undoWrites: readonly Write[]
}

// The default note_kind/cadence a triage conversion writes, since neither
// Part G4's note-kind vocabulary nor Part E1's cadence engine exist yet —
// see docs/phase_B3_inbox_triage.md for why these two specific values.
const CONVERTED_NOTE_KIND = 'idea'
const CONVERTED_ROUTINE_CADENCE = 'daily'

function startOfDay(ms: number): number {
  const d = new Date(ms)
  d.setHours(0, 0, 0, 0)
  return d.getTime()
}

function itemsWrite(id: string, fields: Readonly<Record<string, SqlValue>>): Write {
  return { table: 'items', key: { id }, fields }
}

function taskFieldsWrite(id: string, fields: Readonly<Record<string, SqlValue>>): Write {
  return { table: 'task_fields', key: { item_id: id }, fields }
}

export function planTriageAction(item: TriageItem, action: TriageAction, now: number): TriagePlan {
  switch (action.type) {
    case 'scheduleToday': {
      const scheduledFor = startOfDay(now)
      return {
        label: 'Scheduled for today',
        writes: [
          itemsWrite(item.id, { status: 'active' }),
          taskFieldsWrite(item.id, { scheduled_for: scheduledFor }),
        ],
        undoWrites: [
          itemsWrite(item.id, { status: item.status }),
          taskFieldsWrite(item.id, { scheduled_for: item.scheduledFor }),
        ],
      }
    }
    case 'scheduleDate': {
      return {
        label: 'Scheduled',
        writes: [
          itemsWrite(item.id, { status: 'active' }),
          taskFieldsWrite(item.id, { scheduled_for: action.date }),
        ],
        undoWrites: [
          itemsWrite(item.id, { status: item.status }),
          taskFieldsWrite(item.id, { scheduled_for: item.scheduledFor }),
        ],
      }
    }
    case 'fileToProject': {
      return {
        label: `Filed to ${action.projectTitle}`,
        writes: [
          itemsWrite(item.id, { status: 'active' }),
          {
            table: 'links',
            key: { from_id: item.id, to_id: action.projectId, rel: 'project' },
            fields: { created_at: now },
          },
        ],
        undoWrites: [
          itemsWrite(item.id, { status: item.status }),
          {
            table: 'links',
            key: { from_id: item.id, to_id: action.projectId, rel: 'project' },
            fields: { deleted_at: now },
          },
        ],
      }
    }
    case 'convertToNote': {
      return {
        label: 'Converted to note',
        writes: [
          itemsWrite(item.id, { kind: 'note', status: null }),
          {
            table: 'note_fields',
            key: { item_id: item.id },
            fields: { note_kind: CONVERTED_NOTE_KIND },
          },
        ],
        undoWrites: [itemsWrite(item.id, { kind: 'task', status: item.status })],
      }
    }
    case 'convertToRoutine': {
      return {
        label: 'Converted to routine',
        writes: [
          itemsWrite(item.id, { kind: 'routine', status: null }),
          {
            table: 'routine_fields',
            key: { item_id: item.id },
            fields: { cadence: CONVERTED_ROUTINE_CADENCE },
          },
        ],
        undoWrites: [itemsWrite(item.id, { kind: 'task', status: item.status })],
      }
    }
    case 'someday': {
      return {
        label: 'Moved to someday',
        writes: [
          itemsWrite(item.id, { status: 'active' }),
          taskFieldsWrite(item.id, { someday: 1 }),
        ],
        undoWrites: [
          itemsWrite(item.id, { status: item.status }),
          taskFieldsWrite(item.id, { someday: item.someday }),
        ],
      }
    }
    case 'done': {
      return {
        label: 'Marked done',
        writes: [
          itemsWrite(item.id, { status: 'active' }),
          taskFieldsWrite(item.id, { completed_at: now }),
        ],
        undoWrites: [
          itemsWrite(item.id, { status: item.status }),
          taskFieldsWrite(item.id, { completed_at: item.completedAt }),
        ],
      }
    }
    case 'delete': {
      return {
        label: 'Deleted',
        writes: [itemsWrite(item.id, { deleted_at: now })],
        undoWrites: [itemsWrite(item.id, { deleted_at: null })],
      }
    }
  }
}
