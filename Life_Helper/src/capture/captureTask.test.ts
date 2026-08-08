import { describe, expect, it, vi } from 'vitest'
import { captureTask } from './captureTask'
import type { MutateResult } from '../db/ops'

const NOOP_RESULT: MutateResult = { touchedTables: new Set(), opsInserted: 0 }

describe('captureTask', () => {
  it('writes an items row (kind=task, status=inbox) and its task_fields row in one mutate() call', async () => {
    const mutate = vi.fn().mockResolvedValue(NOOP_RESULT)
    const id = await captureTask(
      { title: 'Buy milk' },
      { mutate, generateId: () => 'fixed-id', now: () => 1000 },
    )

    expect(id).toBe('fixed-id')
    expect(mutate).toHaveBeenCalledTimes(1)
    expect(mutate).toHaveBeenCalledWith({
      writes: [
        {
          table: 'items',
          key: { id: 'fixed-id' },
          fields: {
            kind: 'task',
            title: 'Buy milk',
            status: 'inbox',
            created_at: 1000,
            updated_at: 1000,
          },
        },
        {
          table: 'task_fields',
          key: { item_id: 'fixed-id' },
          fields: {},
        },
      ],
    })
  })

  it('trims surrounding whitespace from the title', async () => {
    const mutate = vi.fn().mockResolvedValue(NOOP_RESULT)
    await captureTask({ title: '  Buy milk  \n' }, { mutate, generateId: () => 'id', now: () => 1 })
    const call = mutate.mock.calls[0][0] as { writes: { fields: { title: string } }[] }
    expect(call.writes[0].fields.title).toBe('Buy milk')
  })

  it('writes scheduled_for onto task_fields when provided', async () => {
    const mutate = vi.fn().mockResolvedValue(NOOP_RESULT)
    await captureTask(
      { title: 'Buy milk', scheduledFor: 123_456 },
      { mutate, generateId: () => 'id', now: () => 1 },
    )
    const call = mutate.mock.calls[0][0] as {
      writes: { table: string; fields: Record<string, unknown> }[]
    }
    expect(call.writes[1]).toMatchObject({
      table: 'task_fields',
      fields: { scheduled_for: 123_456 },
    })
  })

  it('writes estimate_min onto task_fields when provided', async () => {
    const mutate = vi.fn().mockResolvedValue(NOOP_RESULT)
    await captureTask(
      { title: 'Buy milk', estimateMin: 45 },
      { mutate, generateId: () => 'id', now: () => 1 },
    )
    const call = mutate.mock.calls[0][0] as {
      writes: { table: string; fields: Record<string, unknown> }[]
    }
    expect(call.writes[1]).toMatchObject({
      table: 'task_fields',
      fields: { estimate_min: 45 },
    })
  })

  it('omits scheduled_for/estimate_min from task_fields entirely when null or absent', async () => {
    const mutate = vi.fn().mockResolvedValue(NOOP_RESULT)
    await captureTask(
      { title: 'Buy milk', scheduledFor: null, estimateMin: null },
      { mutate, generateId: () => 'id', now: () => 1 },
    )
    const call = mutate.mock.calls[0][0] as {
      writes: { table: string; fields: Record<string, unknown> }[]
    }
    expect(call.writes[1].fields).toEqual({})
  })

  it('writes nothing and returns null for blank input', async () => {
    const mutate = vi.fn().mockResolvedValue(NOOP_RESULT)
    const id = await captureTask({ title: '   ' }, { mutate })
    expect(id).toBeNull()
    expect(mutate).not.toHaveBeenCalled()
  })

  it('writes nothing and returns null for empty input', async () => {
    const mutate = vi.fn().mockResolvedValue(NOOP_RESULT)
    const id = await captureTask({ title: '' }, { mutate })
    expect(id).toBeNull()
    expect(mutate).not.toHaveBeenCalled()
  })

  it('defaults to a real UUIDv7 id and the current time when not injected', async () => {
    const mutate = vi.fn().mockResolvedValue(NOOP_RESULT)
    const id = await captureTask({ title: 'Buy milk' }, { mutate })
    expect(id).toMatch(/^[0-9a-f-]{36}$/)
    expect(mutate).toHaveBeenCalledTimes(1)
  })
})
