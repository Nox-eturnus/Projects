import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { startOfLocalDay } from '../scheduling/localDay'
import { RouterProvider } from '../ui/router'
import { THRESHOLD_KEY, UNDO_WINDOW_MS, type EligibleTask, type SweepRow } from './amnesty'

const { mutateMock, queryMock } = vi.hoisted(() => ({
  mutateMock: vi.fn(),
  queryMock: vi.fn(),
}))

vi.mock('../db/client', () => ({
  dbClient: {
    mutate: (input: unknown) => mutateMock(input) as Promise<unknown>,
    query: (sql: string, params: unknown[]) => queryMock(sql, params) as Promise<unknown>,
    getDeviceId: () => Promise.resolve('device-1'),
    subscribe: () => () => undefined,
  },
}))

const { FreshStart } = await import('./FreshStart')

const NOW = Date.now()
const TODAY = startOfLocalDay(NOW)

function eligible(...ids: string[]): EligibleTask[] {
  return ids.map((id) => ({ id, title: id, status: 'active' }))
}

function serve(data: { eligible?: EligibleTask[]; sweep?: SweepRow; swept?: string[] }) {
  queryMock.mockImplementation((sql: string, params: unknown[]) => {
    if (sql.includes('FROM amnesty_sweeps')) return Promise.resolve(data.sweep ? [data.sweep] : [])
    if (sql.includes('amnesty_sweep_id = ?')) {
      return Promise.resolve((data.swept ?? []).map((item_id) => ({ item_id, params })))
    }
    if (sql.includes('FROM items')) return Promise.resolve(data.eligible ?? [])
    return Promise.resolve([])
  })
}

function renderFreshStart(onUndoable = vi.fn()) {
  render(
    <RouterProvider>
      <FreshStart todayStart={TODAY} now={NOW} onUndoable={onUndoable} />
    </RouterProvider>,
  )
  return onUndoable
}

interface MutateCall {
  writes: { table: string; key: Record<string, string>; fields: Record<string, unknown> }[]
}

function lastMutate(): MutateCall {
  return mutateMock.mock.calls.at(-1)?.[0] as MutateCall
}

const user = () => userEvent.setup({ delay: null })

beforeEach(() => {
  mutateMock.mockReset().mockResolvedValue({ touchedTables: new Set(), opsInserted: 0 })
  queryMock.mockReset()
  window.localStorage.clear()
})

describe('FreshStart', () => {
  it('shows nothing when nothing is old enough and no sweep can be undone', async () => {
    serve({})
    renderFreshStart()
    // Loaded: the (closed) confirmation sheet is mounted once the queries are back.
    await screen.findByRole('heading', { name: 'Fresh start', hidden: true })
    expect(screen.queryByRole('region', { name: 'Fresh start' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Fresh start' })).toBeNull()
  })

  it('offers a fresh start without a count; the confirmation shows the count', async () => {
    serve({ eligible: eligible('a', 'b', 'c') })
    renderFreshStart()
    const offer = await screen.findByRole('region', { name: 'Fresh start' })
    expect(offer.textContent).toMatch(/untouched for 30 days or more/)
    expect(offer.textContent).not.toMatch(/\b3\b/)

    await user().click(screen.getByRole('button', { name: 'Fresh start' }))
    expect(
      screen.getByText('Move 3 tasks untouched for 30 days or more to Someday?'),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: 'Move 3 to Someday', hidden: true }),
    ).toBeInTheDocument()
  })

  it('the sweep writes exactly the counted tasks, and is undoable at once', async () => {
    serve({ eligible: eligible('a', 'b') })
    const onUndoable = renderFreshStart()
    const u = user()
    await u.click(await screen.findByRole('button', { name: 'Fresh start' }))
    await u.click(screen.getByRole('button', { name: 'Move 2 to Someday', hidden: true }))

    const writes = lastMutate().writes
    expect(writes[0]).toMatchObject({
      table: 'amnesty_sweeps',
      fields: { threshold_days: 30, item_count: 2 },
    })
    const moved = writes.filter((w) => w.table === 'task_fields')
    expect(moved.map((w) => w.key.item_id)).toEqual(['a', 'b'])
    expect(moved[0].fields).toMatchObject({ someday: 1 })
    expect(onUndoable).toHaveBeenCalledWith('Moved to Someday', expect.any(Function))
  })

  it('"Not now" closes it without writing anything', async () => {
    serve({ eligible: eligible('a') })
    renderFreshStart()
    const u = user()
    await u.click(await screen.findByRole('button', { name: 'Fresh start' }))
    expect(
      screen.getByText('Move 1 task untouched for 30 days or more to Someday?'),
    ).toBeInTheDocument()
    await u.click(screen.getByRole('button', { name: 'Not now', hidden: true }))
    expect(mutateMock).not.toHaveBeenCalled()
  })

  it('uses the threshold from Settings', async () => {
    window.localStorage.setItem(THRESHOLD_KEY, '14')
    serve({ eligible: eligible('a') })
    renderFreshStart()
    expect(await screen.findByText(/untouched for 14 days or more/)).toBeInTheDocument()
  })

  it('for 24 hours after a sweep, offers to undo it — restoring the tasks it moved', async () => {
    const sweep: SweepRow = {
      id: 'sweep-1',
      swept_at: NOW - 2 * 60 * 60 * 1000,
      threshold_days: 30,
      item_count: 2,
      undone_at: null,
    }
    serve({ eligible: eligible('later'), sweep, swept: ['a', 'b'] })
    renderFreshStart()
    const note = await screen.findByRole('region', { name: 'Fresh start' })
    expect(note.textContent).toMatch(/You can undo it until/)
    expect(note.textContent).not.toMatch(/\b2\b/)

    await user().click(screen.getByRole('button', { name: 'Undo fresh start' }))
    await vi.waitFor(() => {
      expect(mutateMock).toHaveBeenCalled()
    })
    const writes = lastMutate().writes
    expect(writes.filter((w) => w.table === 'task_fields').map((w) => w.key.item_id)).toEqual([
      'a',
      'b',
    ])
    expect(writes.at(-1)).toMatchObject({ table: 'amnesty_sweeps', key: { id: 'sweep-1' } })
  })

  it('after 24 hours, the undo is gone and the offer is back', async () => {
    const sweep: SweepRow = {
      id: 'sweep-1',
      swept_at: NOW - UNDO_WINDOW_MS - 1,
      threshold_days: 30,
      item_count: 2,
      undone_at: null,
    }
    serve({ eligible: eligible('a'), sweep })
    renderFreshStart()
    expect(await screen.findByRole('button', { name: 'Fresh start' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Undo fresh start' })).toBeNull()
  })
})
