import { describe, expect, it } from 'vitest'
import { planTriageAction, type TriageAction, type TriageItem } from './triageActions'

const NOW = 1_700_000_000_000 // an arbitrary fixed instant

const BASE_ITEM: TriageItem = {
  id: 'item-1',
  status: 'inbox',
  dueAt: null,
  scheduledFor: null,
  deferUntil: null,
  touchCount: 0,
  lastTouchedAt: null,
  someday: 0,
  completedAt: null,
}

const START_OF_TODAY = new Date(NOW).setHours(0, 0, 0, 0)
const DAY_MS = 24 * 60 * 60 * 1000

describe('planTriageAction', () => {
  it('scheduleToday: sets status active and scheduled_for to the start of today', () => {
    const plan = planTriageAction(BASE_ITEM, { type: 'scheduleToday' }, NOW)
    expect(plan.writes).toEqual([
      { table: 'items', key: { id: 'item-1' }, fields: { status: 'active' } },
      {
        table: 'task_fields',
        key: { item_id: 'item-1' },
        fields: { scheduled_for: new Date(NOW).setHours(0, 0, 0, 0) },
      },
    ])
  })

  it('scheduleToday: undo restores the prior status and scheduled_for', () => {
    // Captured as "tomorrow 3pm", triaged to today: pulled in, not a reschedule.
    const tomorrow3pm = START_OF_TODAY + DAY_MS + 15 * 60 * 60 * 1000
    const item: TriageItem = { ...BASE_ITEM, scheduledFor: tomorrow3pm }
    const plan = planTriageAction(item, { type: 'scheduleToday' }, NOW)
    expect(plan.undoWrites).toEqual([
      { table: 'items', key: { id: 'item-1' }, fields: { status: 'inbox' } },
      { table: 'task_fields', key: { item_id: 'item-1' }, fields: { scheduled_for: tomorrow3pm } },
    ])
  })

  it('scheduleToday: an item already scheduled earlier than today counts as a reschedule', () => {
    const item: TriageItem = {
      ...BASE_ITEM,
      scheduledFor: START_OF_TODAY - 2 * DAY_MS,
      touchCount: 1,
      lastTouchedAt: 7,
    }
    const plan = planTriageAction(item, { type: 'scheduleToday' }, NOW)
    expect(plan.writes).toContainEqual({
      table: 'task_fields',
      key: { item_id: 'item-1' },
      fields: { scheduled_for: START_OF_TODAY, touch_count: 2, last_touched_at: NOW },
    })
    expect(plan.undoWrites).toContainEqual({
      table: 'task_fields',
      key: { item_id: 'item-1' },
      fields: { scheduled_for: item.scheduledFor, touch_count: 1, last_touched_at: 7 },
    })
  })

  it('scheduleToday: an item already scheduled for today writes only the status', () => {
    const item: TriageItem = { ...BASE_ITEM, scheduledFor: START_OF_TODAY }
    const plan = planTriageAction(item, { type: 'scheduleToday' }, NOW)
    expect(plan.writes).toEqual([
      { table: 'items', key: { id: 'item-1' }, fields: { status: 'active' } },
    ])
  })

  it('scheduleDate: sets scheduled_for to the given date', () => {
    const plan = planTriageAction(BASE_ITEM, { type: 'scheduleDate', date: 123_456 }, NOW)
    expect(plan.writes).toContainEqual({
      table: 'task_fields',
      key: { item_id: 'item-1' },
      fields: { scheduled_for: 123_456 },
    })
  })

  it('scheduleDate: moving a captured date to a later day increments touch_count once', () => {
    const item: TriageItem = { ...BASE_ITEM, scheduledFor: START_OF_TODAY + DAY_MS }
    const plan = planTriageAction(
      item,
      { type: 'scheduleDate', date: START_OF_TODAY + 5 * DAY_MS },
      NOW,
    )
    expect(plan.writes).toContainEqual({
      table: 'task_fields',
      key: { item_id: 'item-1' },
      fields: { scheduled_for: START_OF_TODAY + 5 * DAY_MS, touch_count: 1, last_touched_at: NOW },
    })
  })

  it('fileToProject: creates a project link and undo tombstones it', () => {
    const plan = planTriageAction(
      BASE_ITEM,
      { type: 'fileToProject', projectId: 'project-1', projectTitle: 'Website' },
      NOW,
    )
    expect(plan.label).toBe('Filed to Website')
    expect(plan.writes).toContainEqual({
      table: 'links',
      key: { from_id: 'item-1', to_id: 'project-1', rel: 'project' },
      fields: { created_at: NOW },
    })
    expect(plan.undoWrites).toContainEqual({
      table: 'links',
      key: { from_id: 'item-1', to_id: 'project-1', rel: 'project' },
      fields: { deleted_at: NOW },
    })
  })

  it('convertToNote: changes kind to note, clears status, creates note_fields', () => {
    const plan = planTriageAction(BASE_ITEM, { type: 'convertToNote' }, NOW)
    expect(plan.writes).toEqual([
      { table: 'items', key: { id: 'item-1' }, fields: { kind: 'note', status: null } },
      { table: 'note_fields', key: { item_id: 'item-1' }, fields: { note_kind: 'idea' } },
    ])
    expect(plan.undoWrites).toEqual([
      { table: 'items', key: { id: 'item-1' }, fields: { kind: 'task', status: 'inbox' } },
    ])
  })

  it('convertToRoutine: changes kind to routine, clears status, creates routine_fields', () => {
    const plan = planTriageAction(BASE_ITEM, { type: 'convertToRoutine' }, NOW)
    expect(plan.writes).toEqual([
      { table: 'items', key: { id: 'item-1' }, fields: { kind: 'routine', status: null } },
      { table: 'routine_fields', key: { item_id: 'item-1' }, fields: { cadence: 'daily' } },
    ])
    expect(plan.undoWrites).toEqual([
      { table: 'items', key: { id: 'item-1' }, fields: { kind: 'task', status: 'inbox' } },
    ])
  })

  it('someday: sets the someday flag and undo restores it', () => {
    const item: TriageItem = { ...BASE_ITEM, someday: 0 }
    const plan = planTriageAction(item, { type: 'someday' }, NOW)
    expect(plan.writes).toContainEqual({
      table: 'task_fields',
      key: { item_id: 'item-1' },
      fields: { someday: 1 },
    })
    expect(plan.undoWrites).toContainEqual({
      table: 'task_fields',
      key: { item_id: 'item-1' },
      fields: { someday: 0 },
    })
  })

  it('done: sets completed_at to now and undo clears it', () => {
    const plan = planTriageAction(BASE_ITEM, { type: 'done' }, NOW)
    expect(plan.writes).toContainEqual({
      table: 'task_fields',
      key: { item_id: 'item-1' },
      fields: { completed_at: NOW },
    })
    expect(plan.undoWrites).toContainEqual({
      table: 'task_fields',
      key: { item_id: 'item-1' },
      fields: { completed_at: null },
    })
  })

  it('delete: tombstones the item and undo clears deleted_at', () => {
    const plan = planTriageAction(BASE_ITEM, { type: 'delete' }, NOW)
    expect(plan.writes).toEqual([
      { table: 'items', key: { id: 'item-1' }, fields: { deleted_at: NOW } },
    ])
    expect(plan.undoWrites).toEqual([
      { table: 'items', key: { id: 'item-1' }, fields: { deleted_at: null } },
    ])
  })

  it('every action label is a short human-readable string', () => {
    const actions: TriageAction[] = [
      { type: 'scheduleToday' },
      { type: 'scheduleDate', date: 1 },
      { type: 'fileToProject', projectId: 'p', projectTitle: 'Website' },
      { type: 'convertToNote' },
      { type: 'convertToRoutine' },
      { type: 'someday' },
      { type: 'done' },
      { type: 'delete' },
    ]
    for (const action of actions) {
      const plan = planTriageAction(BASE_ITEM, action, NOW)
      expect(plan.label.length).toBeGreaterThan(0)
    }
  })
})
