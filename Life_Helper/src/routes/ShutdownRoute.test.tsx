import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { RouterProvider } from '../ui/router'
import { addLocalDays, localDayKey, startOfLocalDay } from '../scheduling/localDay'
import type { DayPlanRow } from '../today/dayPlan'
import type { DayTask } from '../today/proposal'

type ChangeListener = (tables: string[]) => void

const { mutateMock, queryMock, listeners } = vi.hoisted(() => ({
  mutateMock: vi.fn(),
  queryMock: vi.fn(),
  listeners: new Set<ChangeListener>(),
}))

vi.mock('../db/client', () => ({
  dbClient: {
    mutate: (input: unknown) => mutateMock(input) as Promise<unknown>,
    query: (sql: string, params: unknown[]) => queryMock(sql, params) as Promise<unknown>,
    getDeviceId: () => Promise.resolve('device-1'),
    subscribe: (listener: ChangeListener) => {
      listeners.add(listener)
      return () => listeners.delete(listener)
    },
  },
}))

const { ShutdownRoute } = await import('./ShutdownRoute')

const DAY_MS = 24 * 60 * 60 * 1000
const TODAY = startOfLocalDay(Date.now())
const TOMORROW = addLocalDays(TODAY, 1)
const TODAY_KEY = localDayKey(TODAY)
const TOMORROW_KEY = localDayKey(TOMORROW)

function task(id: string, overrides: Partial<DayTask> = {}): DayTask {
  return {
    id,
    title: id,
    status: 'active',
    created_at: 1_000,
    due_at: null,
    scheduled_for: TOMORROW,
    defer_until: null,
    touch_count: 0,
    last_touched_at: null,
    completed_at: null,
    ...overrides,
  }
}

function serve(data: { tasks?: DayTask[]; plans?: DayPlanRow[]; lastActiveAt?: number }) {
  queryMock.mockImplementation((sql: string) => {
    if (sql.includes('FROM day_plans')) return Promise.resolve(data.plans ?? [])
    if (sql.includes('FROM ops')) {
      return Promise.resolve([{ last_active_at: data.lastActiveAt ?? Date.now() }])
    }
    if (sql.includes('FROM items')) return Promise.resolve(data.tasks ?? [])
    return Promise.resolve([])
  })
}

function renderShutdown() {
  return render(
    <RouterProvider>
      <ShutdownRoute />
    </RouterProvider>,
  )
}

interface MutateCall {
  writes: { table: string; key: Record<string, string>; fields: Record<string, unknown> }[]
}

function lastMutate(): MutateCall {
  return mutateMock.mock.calls.at(-1)?.[0] as MutateCall
}

/** The picked tasks' titles, in pick order (by their numbered markers). */
function pressedTitles(): string[] {
  return screen
    .getAllByRole('button', { pressed: true })
    .map((button) => {
      const labelId = button.getAttribute('aria-labelledby') ?? ''
      const marker = button.querySelector('[aria-hidden="true"]')?.textContent ?? ''
      return [Number(marker), document.getElementById(labelId)?.textContent ?? ''] as const
    })
    .sort((a, b) => a[0] - b[0])
    .map(([, title]) => title)
}

const TASKS = [
  task('Done this morning', { scheduled_for: TODAY, completed_at: Date.now() }),
  task('Still open today', { scheduled_for: TODAY }),
  task('A'),
  task('B'),
  task('C'),
  task('D'),
]

beforeEach(() => {
  mutateMock.mockReset().mockResolvedValue({ touchedTables: new Set(), opsInserted: 0 })
  queryMock.mockReset()
  listeners.clear()
  window.history.pushState(null, '', '/shutdown')
})

describe('ShutdownRoute: review, then tomorrow’s three', () => {
  it('reviews what got done and what is still open, and can tick one off', async () => {
    serve({ tasks: TASKS })
    const user = userEvent.setup({ delay: null })
    renderShutdown()

    const review = await screen.findByRole('region', { name: 'Today' })
    expect(within(review).getByText('Done this morning')).toBeInTheDocument()
    await user.click(within(review).getByRole('checkbox', { name: 'Still open today' }))
    expect(lastMutate().writes[0]).toMatchObject({
      table: 'task_fields',
      key: { item_id: 'Still open today' },
    })
  })

  it('preselects three (carried-over work first) and commits them with the shutdown in one write', async () => {
    serve({ tasks: TASKS })
    const user = userEvent.setup({ delay: null })
    renderShutdown()

    await user.click(await screen.findByRole('button', { name: /Next: tomorrow/ }))
    // Today's unfinished task is carried over, so it leads tomorrow's picks.
    expect(pressedTitles()).toEqual(['Still open today', 'A', 'B'])

    await user.click(screen.getByRole('button', { name: "Set tomorrow's three" }))
    const writes = lastMutate().writes
    expect(writes.find((w) => w.key.day === TOMORROW_KEY)?.fields).toMatchObject({
      top1_id: 'Still open today',
      top2_id: 'A',
      top3_id: 'B',
      committed_via: 'shutdown',
    })
    expect(writes.find((w) => w.key.day === TODAY_KEY)?.fields).toEqual({
      shutdown_completed_at: expect.any(Number) as unknown,
    })
    expect(screen.getByRole('heading', { name: 'Tomorrow is set.' })).toBeInTheDocument()
  })

  it('caps the picks at three, and a pick can be swapped by unpicking first', async () => {
    serve({ tasks: TASKS })
    const user = userEvent.setup({ delay: null })
    renderShutdown()
    await user.click(await screen.findByRole('button', { name: /Next: tomorrow/ }))

    await user.click(screen.getByRole('button', { name: 'C' }))
    expect(screen.getByText('Three is the limit — unpick one first.')).toBeInTheDocument()
    expect(pressedTitles()).not.toContain('C')

    await user.click(screen.getByRole('button', { name: 'A' }))
    await user.click(screen.getByRole('button', { name: 'C' }))
    expect(pressedTitles()).toEqual(['Still open today', 'B', 'C'])
  })

  it('tomorrow already planned: those three are the starting selection', async () => {
    serve({
      tasks: TASKS,
      plans: [
        {
          day: TOMORROW_KEY,
          top1_id: 'D',
          top2_id: null,
          top3_id: null,
          committed_at: 1,
          committed_via: 'shutdown',
          shutdown_completed_at: null,
        },
      ],
    })
    const user = userEvent.setup({ delay: null })
    renderShutdown()
    await user.click(await screen.findByRole('button', { name: /Next: tomorrow/ }))
    expect(pressedTitles()).toEqual(['D'])
    expect(screen.getByRole('button', { name: "Set tomorrow's one" })).toBeInTheDocument()
  })

  it('finishing with nothing picked still completes the shutdown', async () => {
    serve({
      tasks: [task('Done this morning', { scheduled_for: TODAY, completed_at: Date.now() })],
    })
    const user = userEvent.setup({ delay: null })
    renderShutdown()
    await user.click(await screen.findByRole('button', { name: /Next: tomorrow/ }))
    await user.click(screen.getByRole('button', { name: 'Finish without picking' }))
    expect(lastMutate().writes.find((w) => w.key.day === TODAY_KEY)?.fields).toMatchObject({
      shutdown_completed_at: expect.any(Number) as unknown,
    })
  })
})

describe('ShutdownRoute: three states', () => {
  it('empty: nothing to review or plan, one action', async () => {
    serve({})
    renderShutdown()
    expect(await screen.findByText(/Nothing to look back on or plan yet/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Go to Capture' })).toBeInTheDocument()
  })

  it('cold: skips the look back and goes straight to picking', async () => {
    serve({ tasks: TASKS, lastActiveAt: Date.now() - 5 * DAY_MS })
    renderShutdown()
    expect(await screen.findByText(/Welcome back. No need to look back/)).toBeInTheDocument()
    expect(screen.getByRole('region', { name: "Tomorrow's three" })).toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Today' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Back' })).not.toBeInTheDocument()
  })
})

describe('ShutdownRoute: reminder time', () => {
  it('defaults to 8pm and remembers a change', async () => {
    serve({ tasks: TASKS })
    renderShutdown()
    const input = await screen.findByLabelText(/Evening reminder/)
    expect(input).toHaveValue('20:00')
    fireEvent.change(input, { target: { value: '21:30' } })
    expect(window.localStorage.getItem('life-helper-shutdown-time')).toBe('21:30')
  })
})
