import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { SomedayTask } from '../amnesty/amnesty'
import { addLocalDays, startOfLocalDay } from '../scheduling/localDay'
import { RouterProvider } from '../ui/router'

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

const { SomedayRoute } = await import('./SomedayRoute')

const DAY_MS = 24 * 60 * 60 * 1000
const TODAY = startOfLocalDay(Date.now())

function task(id: string, overrides: Partial<SomedayTask> = {}): SomedayTask {
  return {
    id,
    title: id,
    status: 'active',
    created_at: 1_000,
    updated_at: 1_000,
    due_at: null,
    scheduled_for: null,
    defer_until: null,
    touch_count: 0,
    last_touched_at: null,
    completed_at: null,
    estimate_min: null,
    amnesty_sweep_id: 'sweep-1',
    ...overrides,
  }
}

const TASKS = [
  task('Learn sourdough baking', { scheduled_for: addLocalDays(TODAY, -40) }),
  task('Sort the bookshelf', { status: 'inbox' }),
]

function serve(data: { tasks?: SomedayTask[]; lastActiveAt?: number }) {
  queryMock.mockImplementation((sql: string, params: unknown[]) => {
    if (sql.includes('FROM ops')) {
      return Promise.resolve([{ last_active_at: data.lastActiveAt ?? Date.now() }])
    }
    if (sql.includes('FROM items')) {
      const search = params[1] as string
      const tasks = data.tasks ?? []
      // A stand-in for FTS5: the route passes the escaped query through.
      if (search === '') return Promise.resolve(tasks)
      const words = [...search.matchAll(/"([^"]+)"\*/g)].map((m) => m[1].toLowerCase())
      return Promise.resolve(
        tasks.filter((t) => words.every((w) => t.title.toLowerCase().includes(w))),
      )
    }
    return Promise.resolve([])
  })
}

function renderSomeday() {
  return render(
    <RouterProvider>
      <SomedayRoute />
    </RouterProvider>,
  )
}

interface MutateCall {
  writes: { table: string; key: Record<string, string>; fields: Record<string, unknown> }[]
}

function lastMutate(): MutateCall {
  return mutateMock.mock.calls.at(-1)?.[0] as MutateCall
}

const user = () => userEvent.setup({ delay: null })

/** Decision 4 and 7: no counts of what's set aside, and nothing framed as failure. */
const NOT_ALLOWED = /overdue|late\b|behind|fail|missed|neglect|abandon|forgot|\d+ (tasks|items)/i

beforeEach(() => {
  mutateMock.mockReset().mockResolvedValue({ touchedTables: new Set(), opsInserted: 0 })
  queryMock.mockReset()
  window.history.pushState(null, '', '/someday')
})

describe('SomedayRoute', () => {
  it('empty: explains what would be here, with one action', async () => {
    serve({})
    const { container } = renderSomeday()
    expect(await screen.findByText(/Nothing in Someday/)).toBeInTheDocument()
    expect(container.textContent).not.toMatch(NOT_ALLOWED)
    await user().click(screen.getByRole('button', { name: 'Go to Today' }))
    expect(window.location.pathname).toBe('/')
  })

  it('loaded: lists what is set aside, with no count', async () => {
    serve({ tasks: TASKS })
    const { container } = renderSomeday()
    expect(await screen.findByText(/Set aside, not gone/)).toBeInTheDocument()
    expect(screen.getAllByRole('listitem')).toHaveLength(2)
    expect(container.textContent).not.toMatch(NOT_ALLOWED)
    expect(container.textContent).not.toMatch(/\b2\b/)
  })

  it('cold: a welcome back, and the list as usual', async () => {
    serve({ tasks: TASKS, lastActiveAt: Date.now() - 10 * DAY_MS })
    const { container } = renderSomeday()
    expect(await screen.findByText(/Welcome back/)).toBeInTheDocument()
    expect(screen.getAllByRole('listitem')).toHaveLength(2)
    expect(container.textContent).not.toMatch(NOT_ALLOWED)
  })

  it('search sends a safe FTS5 query, and a miss says so without looking empty', async () => {
    serve({ tasks: TASKS })
    renderSomeday()
    const u = user()
    const box = await screen.findByLabelText('Search Someday')
    await u.type(box, 'sour')
    expect(queryMock).toHaveBeenCalledWith(expect.stringContaining('items_fts MATCH'), [
      expect.any(Number),
      '"sour"*',
    ])
    expect(await screen.findByText('Learn sourdough baking')).toBeInTheDocument()
    expect(screen.queryByText('Sort the bookshelf')).toBeNull()

    await u.clear(box)
    await u.type(box, 'zzz')
    expect(await screen.findByText(/Nothing in Someday matches/)).toBeInTheDocument()
    expect(screen.queryByText(/Nothing in Someday\. /)).toBeNull()
  })

  it('brings one back to today, undoably', async () => {
    serve({ tasks: TASKS })
    renderSomeday()
    const u = user()
    const row = await screen.findByRole('listitem', { name: 'Learn sourdough baking' })
    await u.click(within(row).getByRole('button', { name: /^Bring back to today/ }))

    const writes = lastMutate().writes
    expect(writes).toContainEqual(
      expect.objectContaining({
        table: 'task_fields',
        fields: { someday: 0, amnesty_sweep_id: null },
      }),
    )
    expect(
      writes.find((w) => w.table === 'task_fields' && 'scheduled_for' in w.fields)?.fields,
    ).toMatchObject({ scheduled_for: TODAY })
    expect(screen.getByText('Brought back to today')).toBeInTheDocument()

    await u.click(screen.getByRole('button', { name: 'Undo' }))
    expect(lastMutate().writes).toContainEqual(
      expect.objectContaining({
        table: 'task_fields',
        fields: { someday: 1, amnesty_sweep_id: 'sweep-1' },
      }),
    )
  })

  it('brings one back to the inbox, leaving its dates alone', async () => {
    serve({ tasks: TASKS })
    renderSomeday()
    const row = await screen.findByRole('listitem', { name: 'Learn sourdough baking' })
    await user().click(within(row).getByRole('button', { name: /^Bring back to the inbox/ }))
    const writes = lastMutate().writes
    expect(writes.find((w) => w.table === 'items')?.fields).toMatchObject({ status: 'inbox' })
    expect(writes.some((w) => 'scheduled_for' in w.fields)).toBe(false)
    expect(screen.getByText('Brought back to the inbox')).toBeInTheDocument()
  })
})
