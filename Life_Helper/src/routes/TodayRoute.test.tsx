import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { RouterProvider } from '../ui/router'
import { addLocalDays, localDayKey, startOfLocalDay } from '../scheduling/localDay'
import type { DayPlanRow } from '../today/dayPlan'
import type { DayTask } from '../today/proposal'
import type { CalendarEvent } from '../../edge/src/contract.js'
import { saveConnection, writeCache, type CalendarCache } from '../calendar/calendarStore'
import { refreshRange } from '../calendar/calendarSync'

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

const { TodayRoute } = await import('./TodayRoute')

const HOUR_MS = 60 * 60 * 1000
const TODAY = startOfLocalDay(Date.now())
const TODAY_KEY = localDayKey(TODAY)

function task(id: string, overrides: Partial<DayTask> = {}): DayTask {
  return {
    id,
    title: id,
    status: 'active',
    created_at: 1_000,
    due_at: null,
    scheduled_for: TODAY,
    defer_until: null,
    touch_count: 0,
    last_touched_at: null,
    completed_at: null,
    estimate_min: null,
    ...overrides,
  }
}

function plan(ids: [string, string?, string?], overrides: Partial<DayPlanRow> = {}): DayPlanRow {
  return {
    day: TODAY_KEY,
    top1_id: ids[0],
    top2_id: ids[1] ?? null,
    top3_id: ids[2] ?? null,
    committed_at: 1,
    committed_via: 'shutdown',
    shutdown_completed_at: null,
    ...overrides,
  }
}

function serve(data: {
  tasks?: DayTask[]
  plans?: DayPlanRow[]
  lastActiveAt?: number
  /** Rows for Part C5's amnesty-eligible query. */
  oldTasks?: { id: string; title: string; status: string }[]
}) {
  queryMock.mockImplementation((sql: string) => {
    if (sql.includes('FROM amnesty_sweeps')) return Promise.resolve([])
    if (sql.includes("'amnesty_sweep_id'")) return Promise.resolve(data.oldTasks ?? [])
    if (sql.includes('FROM day_plans')) return Promise.resolve(data.plans ?? [])
    if (sql.includes('FROM ops')) {
      return Promise.resolve([{ last_active_at: data.lastActiveAt ?? Date.now() }])
    }
    if (sql.includes('FROM items')) return Promise.resolve(data.tasks ?? [])
    return Promise.resolve([])
  })
}

function renderToday() {
  return render(
    <RouterProvider>
      <TodayRoute />
    </RouterProvider>,
  )
}

interface MutateCall {
  writes: { table: string; key: Record<string, string>; fields: Record<string, unknown> }[]
}

function lastMutate(): MutateCall {
  return mutateMock.mock.calls.at(-1)?.[0] as MutateCall
}

beforeEach(() => {
  mutateMock.mockReset().mockResolvedValue({ touchedTables: new Set(), opsInserted: 0 })
  queryMock.mockReset()
  listeners.clear()
  window.localStorage.clear()
  window.history.pushState(null, '', '/')
  // No test here may reach a real network: an unexpected refresh fails fast.
  vi.stubGlobal(
    'fetch',
    vi.fn(() => Promise.reject(new TypeError('no network in tests'))),
  )
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('TodayRoute: empty', () => {
  it('explains what would appear here and offers one action', async () => {
    serve({})
    renderToday()
    expect(await screen.findByText(/Nothing lined up for today/)).toBeInTheDocument()
    await userEvent
      .setup({ delay: null })
      .click(screen.getByRole('button', { name: 'Capture something' }))
    expect(window.location.pathname).toBe('/capture')
  })
})

describe('TodayRoute: fresh start (Part C5)', () => {
  it('is one action from Today — even when Today itself is empty', async () => {
    serve({
      oldTasks: [
        { id: 'a', title: 'Old idea', status: 'active' },
        { id: 'b', title: 'Older idea', status: 'inbox' },
      ],
    })
    renderToday()
    expect(await screen.findByText(/Nothing lined up for today/)).toBeInTheDocument()
    const u = userEvent.setup({ delay: null })
    await u.click(await screen.findByRole('button', { name: 'Fresh start' }))
    await u.click(screen.getByRole('button', { name: 'Move 2 to Someday', hidden: true }))
    expect(lastMutate().writes.filter((w) => w.table === 'task_fields')).toHaveLength(2)
    // Undoable at once from Today's own toast.
    expect(screen.getByText('Moved to Someday')).toBeInTheDocument()
  })

  it('stays out of the way when nothing is old enough', async () => {
    serve({ tasks: [task('Today task')] })
    renderToday()
    await screen.findByText('Today task')
    expect(screen.queryByRole('button', { name: 'Fresh start' })).toBeNull()
  })
})

describe('TodayRoute: shutdown skipped — a proposal, one tap to accept or swap', () => {
  const tasks = [
    task('Newest scheduled', { created_at: 4_000 }),
    task('Due this afternoon', { due_at: TODAY + 15 * HOUR_MS, scheduled_for: null }),
    task('From yesterday', { scheduled_for: addLocalDays(TODAY, -1) }),
    task('Oldest scheduled', { created_at: 500 }),
  ]

  it('proposes three: due, then carried over, then oldest scheduled', async () => {
    serve({ tasks })
    renderToday()
    const section = await screen.findByRole('region', { name: 'Three to start with' })
    const titles = within(section)
      .getAllByRole('listitem')
      .map((li) => li.textContent)
    expect(titles[0]).toContain('Due this afternoon')
    expect(titles[1]).toContain('From yesterday')
    expect(titles[2]).toContain('Oldest scheduled')
    expect(within(section).queryByText('Newest scheduled')).not.toBeInTheDocument()
    // The fourth isn't lost — it's in the secondary list below.
    expect(screen.getByRole('region', { name: 'Also today' })).toHaveTextContent('Newest scheduled')
  })

  it('accepting commits exactly those three to today, with an undo', async () => {
    serve({ tasks })
    const user = userEvent.setup({ delay: null })
    renderToday()
    await user.click(await screen.findByRole('button', { name: 'Accept these three' }))

    const planWrite = lastMutate().writes.find((w) => w.table === 'day_plans')
    expect(planWrite).toEqual({
      table: 'day_plans',
      key: { day: TODAY_KEY },
      fields: expect.objectContaining({
        top1_id: 'Due this afternoon',
        top2_id: 'From yesterday',
        top3_id: 'Oldest scheduled',
        committed_via: 'proposal',
      }) as unknown,
    })

    await user.click(screen.getByRole('button', { name: 'Undo' }))
    expect(lastMutate().writes.find((w) => w.table === 'day_plans')?.fields).toMatchObject({
      top1_id: null,
      committed_at: null,
    })
  })

  it('swapping replaces one with the next candidate in line', async () => {
    serve({ tasks })
    const user = userEvent.setup({ delay: null })
    renderToday()
    await user.click(await screen.findByRole('button', { name: 'Swap From yesterday' }))
    const section = screen.getByRole('region', { name: 'Three to start with' })
    expect(within(section).queryByText('From yesterday')).not.toBeInTheDocument()
    expect(within(section).getByText('Newest scheduled')).toBeInTheDocument()
  })

  it('swap is unavailable when there is nothing else to swap in', async () => {
    serve({ tasks: tasks.slice(0, 2) })
    renderToday()
    expect(await screen.findByRole('button', { name: 'Swap Newest scheduled' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Accept these two' })).toBeInTheDocument()
  })
})

describe('TodayRoute: committed three', () => {
  const tasks = [task('One'), task('Two'), task('Three'), task('Something else')]

  it('shows the committed three prominently, with the rest of today below', async () => {
    serve({ tasks, plans: [plan(['One', 'Two', 'Three'])] })
    renderToday()
    const top = await screen.findByRole('region', { name: 'Your three' })
    expect(within(top).getAllByRole('checkbox')).toHaveLength(3)
    expect(screen.getByRole('region', { name: 'Also today' })).toHaveTextContent('Something else')
    expect(screen.queryByRole('button', { name: /Accept/ })).not.toBeInTheDocument()
  })

  it('ticking one off records it as done', async () => {
    serve({ tasks, plans: [plan(['One', 'Two', 'Three'])] })
    const user = userEvent.setup({ delay: null })
    renderToday()
    await user.click(await screen.findByRole('checkbox', { name: 'Two' }))
    expect(lastMutate().writes[0]).toMatchObject({
      table: 'task_fields',
      key: { item_id: 'Two' },
      fields: { completed_at: expect.any(Number) as unknown },
    })
  })

  it('all three done: a clear finish, and the rest of today stays folded away until asked for', async () => {
    const done = tasks.map((t, i) => (i < 3 ? { ...t, completed_at: Date.now() } : t))
    serve({ tasks: done, plans: [plan(['One', 'Two', 'Three'])] })
    const user = userEvent.setup({ delay: null })
    renderToday()
    expect(
      await screen.findByText("That's all three. The rest of the day is yours."),
    ).toBeInTheDocument()
    expect(screen.queryByText('Something else')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Show the rest of today' }))
    expect(screen.getByText('Something else')).toBeInTheDocument()
  })

  it('a plan for another day is ignored — top 3 are scoped to their date', async () => {
    serve({ tasks, plans: [plan(['One', 'Two', 'Three'], { day: '1999-01-01' })] })
    renderToday()
    expect(await screen.findByRole('region', { name: 'Three to start with' })).toBeInTheDocument()
  })
})

describe('TodayRoute: cold', () => {
  it('after 3+ days away: a welcome and a fresh three, no carried-over list, no counts', async () => {
    serve({
      tasks: [task('A'), task('B'), task('C'), task('D')],
      lastActiveAt: Date.now() - 4 * 24 * HOUR_MS,
    })
    renderToday()
    expect(await screen.findByText('Welcome back. No catching up needed.')).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Three to start with' })).toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Also today' })).not.toBeInTheDocument()
    expect(document.body.textContent).not.toMatch(/overdue|missed|behind/i)
  })
})

describe('TodayRoute: evening shutdown prompt (the notification hook)', () => {
  it('appears once the reminder time has passed, and links to the shutdown', async () => {
    window.localStorage.setItem('life-helper-shutdown-time', '00:00')
    serve({ tasks: [task('A')] })
    const user = userEvent.setup({ delay: null })
    renderToday()
    await user.click(await screen.findByRole('button', { name: 'Start shutdown' }))
    expect(window.location.pathname).toBe('/shutdown')
  })

  it("is gone once tonight's shutdown is done", async () => {
    window.localStorage.setItem('life-helper-shutdown-time', '00:00')
    serve({ tasks: [task('A')], plans: [plan(['A'], { shutdown_completed_at: 1 })] })
    renderToday()
    expect(await screen.findByText('Tomorrow is planned.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Start shutdown' })).not.toBeInTheDocument()
  })
})

describe('TodayRoute: calendar and capacity (Part C3)', () => {
  const HOUR = 60 * 60 * 1000
  const EVENTS: CalendarEvent[] = [
    {
      id: 'standup',
      title: 'Standup',
      allDay: false,
      start: TODAY + 9 * HOUR,
      end: TODAY + 9.5 * HOUR,
      busy: true,
    },
    {
      id: 'bday',
      title: "Sam's birthday",
      allDay: true,
      startDate: TODAY_KEY,
      endDate: '9999-12-31',
      busy: true,
    },
  ]

  function connect(cache: Partial<CalendarCache> = {}) {
    saveConnection({ edgeUrl: 'https://edge.example.workers.dev', deviceKey: 'k'.repeat(43) })
    const range = refreshRange(Date.now())
    writeCache({
      events: EVENTS,
      fetchedAt: Date.now() - 5 * 60_000,
      rangeStart: range.from,
      rangeEnd: range.to,
      // Just attempted: the throttle keeps these tests from refreshing.
      lastAttemptAt: Date.now(),
      problem: null,
      ...cache,
    })
    // A 24-hour waking window with no buffer, so "free time" exists
    // whatever time of day the suite happens to run.
    window.localStorage.setItem(
      'life-helper-capacity-settings',
      JSON.stringify({ wakeStart: '00:00', wakeEnd: '00:00', bufferMinutes: 0 }),
    )
  }

  it("renders today's events from the cache, saying how fresh they are", async () => {
    connect()
    serve({ tasks: [task('A')] })
    renderToday()
    const calendar = await screen.findByRole('region', { name: 'Calendar' })
    expect(within(calendar).getByText('Standup')).toBeInTheDocument()
    expect(within(calendar).getByText("Sam's birthday")).toBeInTheDocument()
    expect(within(calendar).getByText('All day')).toBeInTheDocument()
    expect(within(calendar).getByText('Updated 5 min ago.')).toBeInTheDocument()
  })

  it('offline: still renders from the cache, with a visible staleness indicator', async () => {
    connect({ problem: 'offline', fetchedAt: Date.now() - 3 * HOUR })
    serve({ tasks: [task('A')] })
    renderToday()
    const calendar = await screen.findByRole('region', { name: 'Calendar' })
    expect(within(calendar).getByText('Standup')).toBeInTheDocument()
    expect(within(calendar).getByText(/^Offline — calendar as of/)).toBeInTheDocument()
  })

  it('a revoked grant: a clear reconnect prompt, and the rest of Today still works', async () => {
    connect({ problem: 'reconnect_required' })
    serve({ tasks: [task('A'), task('B')] })
    renderToday()
    expect(await screen.findByText(/Google Calendar needs reconnecting/)).toBeInTheDocument()
    expect(screen.getByText('pnpm calendar:connect')).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Three to start with' })).toBeInTheDocument()
    expect(screen.getByText('Standup')).toBeInTheDocument()
  })

  it('shows free time under the three, and a plain note when their estimates need more', async () => {
    connect()
    serve({ tasks: ['A', 'B', 'C'].map((id) => task(id, { estimate_min: 2000 })) })
    renderToday()
    const top = await screen.findByRole('region', { name: 'Three to start with' })
    expect(within(top).getByText(/free for the rest of today/)).toBeInTheDocument()
    expect(within(top).getByText(/your three need about/)).toHaveTextContent('100h')
    expect(within(top).getByText(/may not all fit today/)).toBeInTheDocument()
  })

  it('no note when the three fit, and tasks without estimates are called out, not guessed', async () => {
    connect()
    serve({ tasks: [task('A', { estimate_min: 1 }), task('B')] })
    renderToday()
    const top = await screen.findByRole('region', { name: 'Three to start with' })
    expect(within(top).getByText(/without an estimate/)).toBeInTheDocument()
    expect(within(top).queryByText(/may not all fit/)).not.toBeInTheDocument()
  })

  it('not connected: no calendar or capacity, just a quiet way to connect', async () => {
    serve({ tasks: [task('A')] })
    renderToday()
    expect(await screen.findByRole('link', { name: 'Connect your calendar' })).toHaveAttribute(
      'href',
      '/settings',
    )
    expect(screen.queryByRole('region', { name: 'Calendar' })).not.toBeInTheDocument()
    expect(screen.queryByText(/free for the rest of today/)).not.toBeInTheDocument()
  })
})
