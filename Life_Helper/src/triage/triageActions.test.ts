import { describe, expect, it } from 'vitest'
import { planTriageAction, type TriageAction, type TriageItem } from './triageActions'

const NOW = 1_700_000_000_000 // an arbitrary fixed instant

const BASE_ITEM: TriageItem = {
  id: 'item-1',
  status: 'inbox',
  scheduledFor: null,
  someday: 0,
  completedAt: null,
}

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
    const item: TriageItem = { ...BASE_ITEM, scheduledFor: 42 }
    const plan = planTriageAction(item, { type: 'scheduleToday' }, NOW)
    expect(plan.undoWrites).toEqual([
      { table: 'items', key: { id: 'item-1' }, fields: { status: 'inbox' } },
      { table: 'task_fields', key: { item_id: 'item-1' }, fields: { scheduled_for: 42 } },
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
