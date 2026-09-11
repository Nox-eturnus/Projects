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
 *
 * The two scheduling actions delegate their `task_fields` write to Part
 * C1's planScheduleChange(), so a triage reschedule to a later day counts
 * against `touch_count` exactly like any other reschedule would.
 */
import type { SqlValue, Write } from '../db/ops.js'
import { atLocalTimeOf, startOfLocalDay } from '../scheduling/localDay.js'
import { planScheduleChange, type TaskSchedule } from '../scheduling/schedule.js'

export interface TriageItem extends TaskSchedule {
  readonly status: string | null
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

function itemsWrite(id: string, fields: Readonly<Record<string, SqlValue>>): Write {
  return { table: 'items', key: { id }, fields }
}

function taskFieldsWrite(id: string, fields: Readonly<Record<string, SqlValue>>): Write {
  return { table: 'task_fields', key: { item_id: id }, fields }
}

/**
 * Moves the item to `day` but keeps the time of day it already had: an
 * item captured as "acne cream 6pm" and triaged to Today stays at 6pm,
 * rather than being flattened to midnight (and one already on `day` isn't
 * written at all). Neither the Today key nor the date picker carries a
 * time, so there's no user intent here to override the captured one. An
 * item with no date yet takes `day` as given.
 */
function planSchedule(item: TriageItem, label: string, day: number, now: number): TriagePlan {
  const scheduledFor = item.scheduledFor === null ? day : atLocalTimeOf(day, item.scheduledFor)
  const schedule = planScheduleChange(item, { scheduledFor }, now)
  return {
    label,
    writes: [itemsWrite(item.id, { status: 'active' }), ...schedule.writes],
    undoWrites: [itemsWrite(item.id, { status: item.status }), ...schedule.undoWrites],
  }
}

export function planTriageAction(item: TriageItem, action: TriageAction, now: number): TriagePlan {
  switch (action.type) {
    case 'scheduleToday':
      return planSchedule(item, 'Scheduled for today', startOfLocalDay(now), now)
    case 'scheduleDate':
      return planSchedule(item, 'Scheduled', action.date, now)
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
