import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { addLocalDays, localDayKey, startOfLocalDay } from '../scheduling/localDay'
import type { SlippingTask } from '../slipping/slippingActions'
import type { DayPlanRow } from '../today/dayPlan'
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

const { RevisitRoute } = await import('./RevisitRoute')

const DAY_MS = 24 * 60 * 60 * 1000
const TODAY = startOfLocalDay(Date.now())
const TODAY_KEY = localDayKey(TODAY)

function task(id: string, overrides: Partial<SlippingTask> = {}): SlippingTask {
  return {
    id,
    title: id,
    status: 'active',
    created_at: 1_000,
    due_at: null,
    scheduled_for: null,
    defer_until: null,
    touch_count: 0,
    last_touched_at: null,
    completed_at: null,
    estimate_min: null,
    project_id: null,
    ...overrides,
  }
}

function plan(ids: string[]): DayPlanRow {
  return {
    day: TODAY_KEY,
    top1_id: ids.at(0) ?? null,
    top2_id: ids.at(1) ?? null,
    top3_id: ids.at(2) ?? null,
    committed_at: 1,
    committed_via: 'shutdown',
    shutdown_completed_at: null,
  }
}

function serve(data: { tasks?: SlippingTask[]; plans?: DayPlanRow[]; lastActiveAt?: number }) {
  queryMock.mockImplementation((sql: string) => {
    if (sql.includes('FROM day_plans')) return Promise.resolve(data.plans ?? [])
    if (sql.includes('FROM ops')) {
      return Promise.resolve([{ last_active_at: data.lastActiveAt ?? Date.now() }])
    }
    if (sql.includes('FROM items')) return Promise.resolve(data.tasks ?? [])
    return Promise.resolve([])
  })
}

function renderRevisit() {
  return render(
    <RouterProvider>
      <RevisitRoute />
    </RouterProvider>,
  )
}

interface MutateCall {
  writes: { table: string; key: Record<string, string>; fields: Record<string, unknown> }[]
}

function lastMutate(): MutateCall {
  return mutateMock.mock.calls.at(-1)?.[0] as MutateCall
}

function card(title: string): HTMLElement {
  return screen.getByRole('listitem', { name: title })
}

const user = () => userEvent.setup({ delay: null })

/**
 * Decision 7's review, as a test: none of this wording may appear anywhere
 * on the page, in any state. "Slipping" is the plan's internal term; the
 * user sees "Revisit".
 */
const GUILT =
  /overdue|late\b|behind|fail|missed|slipp|procrastinat|should have|neglect|ignored|forgot|still not|again\b|\d+ (tasks|items)/i

beforeEach(() => {
  mutateMock.mockReset().mockResolvedValue({ touchedTables: new Set(), opsInserted: 0 })
  queryMock.mockReset()
  window.history.pushState(null, '', '/revisit')
})

const SLIPPING = [
  task('Left alone', { scheduled_for: addLocalDays(TODAY, -12), created_at: TODAY - 12 * DAY_MS }),
  task('Moved four times', {
    touch_count: 4,
    last_touched_at: TODAY - DAY_MS,
    scheduled_for: TODAY,
  }),
  task('Moved once', { touch_count: 1, last_touched_at: TODAY - 3 * DAY_MS }),
  task('Planned today', { scheduled_for: TODAY }),
]

describe('RevisitRoute: empty', () => {
  it('encouraging, not alarming — and one action', async () => {
    serve({ tasks: [task('Planned today', { scheduled_for: TODAY })] })
    const { container } = renderRevisit()
    expect(await screen.findByText(/Nothing needs a second look/)).toBeInTheDocument()
    expect(container.textContent).not.toMatch(GUILT)
    await user().click(screen.getByRole('button', { name: 'Go to Today' }))
    expect(window.location.pathname).toBe('/')
  })
})

describe('RevisitRoute: loaded', () => {
  it('ranks by touch count, then age; leaves out tasks that are not slipping', async () => {
    serve({ tasks: SLIPPING })
    renderRevisit()
    await screen.findByText(/Each one needs a decision/)
    expect(screen.getAllByRole('listitem')).toHaveLength(3)
    const names = screen
      .getAllByRole('listitem')
      .map((li) => within(li).getByText(/^(Left alone|Moved four times|Moved once)$/).textContent)
    expect(names).toEqual(['Moved four times', 'Moved once', 'Left alone'])
  })

  it('each task offers exactly three actions, and says why it is here in plain facts', async () => {
    serve({ tasks: SLIPPING })
    const { container } = renderRevisit()
    await screen.findByText(/Each one needs a decision/)
    const buttons = within(card('Moved four times')).getAllByRole('button')
    expect(buttons.map((b) => b.textContent)).toEqual(['Do it now', 'Break it down', 'Let it go'])
    expect(
      within(card('Moved four times')).getByText(/^Moved 4 times, last on /),
    ).toBeInTheDocument()
    expect(within(card('Left alone')).getByText(/^Planned for /)).toBeInTheDocument()
    expect(container.textContent).not.toMatch(GUILT)
  })

  it("leaves out today's committed three", async () => {
    serve({ tasks: SLIPPING, plans: [plan(['Moved once'])] })
    renderRevisit()
    await screen.findByText(/Each one needs a decision/)
    expect(screen.queryByRole('listitem', { name: 'Moved once' })).toBeNull()
  })
})

describe('RevisitRoute: cold (away 3+ days)', () => {
  it('welcomes back, shows a few rather than the whole list, and no count', async () => {
    const many = Array.from({ length: 6 }, (_, i) =>
      // Touch counts 20…15, so no detail line contains a lone "6".
      task(`Task ${String(i + 1)}`, { touch_count: 20 - i }),
    )
    serve({ tasks: many, lastActiveAt: Date.now() - 5 * DAY_MS })
    const { container } = renderRevisit()
    expect(await screen.findByText(/Welcome back/)).toBeInTheDocument()
    expect(screen.getAllByRole('listitem')).toHaveLength(3)
    expect(container.textContent).not.toMatch(GUILT)
    expect(container.textContent).not.toMatch(/\b6\b/)

    await user().click(screen.getByRole('button', { name: 'Show the rest' }))
    expect(screen.getAllByRole('listitem')).toHaveLength(6)
  })
})

describe('RevisitRoute: do it now', () => {
  it("with a free slot, adds it to today's three — and the toast undoes it", async () => {
    serve({
      tasks: [...SLIPPING, task('In three', { scheduled_for: TODAY })],
      plans: [plan(['In three'])],
    })
    renderRevisit()
    await screen.findByText(/Each one needs a decision/)
    await user().click(within(card('Moved once')).getByRole('button', { name: 'Do it now' }))

    const forward = lastMutate()
    expect(forward.writes.find((w) => w.table === 'day_plans')?.fields).toMatchObject({
      top1_id: 'In three',
      top2_id: 'Moved once',
    })
    expect(screen.getByText("Added to today's three")).toBeInTheDocument()

    await user().click(screen.getByRole('button', { name: 'Undo' }))
    expect(lastMutate().writes.find((w) => w.table === 'day_plans')?.fields).toMatchObject({
      top1_id: 'In three',
      top2_id: null,
    })
  })

  it('with three open slots, asks which one it replaces', async () => {
    const three = ['A', 'B', 'C'].map((id) => task(id, { scheduled_for: TODAY }))
    serve({ tasks: [...SLIPPING, ...three], plans: [plan(['A', 'B', 'C'])] })
    renderRevisit()
    await screen.findByText(/Each one needs a decision/)
    await user().click(within(card('Moved once')).getByRole('button', { name: 'Do it now' }))
    expect(mutateMock).not.toHaveBeenCalled()

    await user().click(screen.getByRole('button', { name: 'Replace B', hidden: true }))
    expect(lastMutate().writes.find((w) => w.table === 'day_plans')?.fields).toMatchObject({
      top1_id: 'A',
      top2_id: 'Moved once',
      top3_id: 'C',
    })
  })

  it('when all three are already done, puts it on today without touching them', async () => {
    const done = ['A', 'B', 'C'].map((id) =>
      task(id, { scheduled_for: TODAY, completed_at: TODAY + 1 }),
    )
    serve({ tasks: [...SLIPPING, ...done], plans: [plan(['A', 'B', 'C'])] })
    renderRevisit()
    await screen.findByText(/Each one needs a decision/)
    await user().click(within(card('Left alone')).getByRole('button', { name: 'Do it now' }))
    const writes = lastMutate().writes
    expect(writes.some((w) => w.table === 'day_plans')).toBe(false)
    expect(writes.find((w) => w.table === 'task_fields')?.fields).toMatchObject({
      scheduled_for: TODAY,
    })
    expect(screen.getByText('Added to today')).toBeInTheDocument()
  })
})

describe('RevisitRoute: break it down', () => {
  it('creates the steps, archives the original, and the toast undoes it', async () => {
    serve({ tasks: SLIPPING })
    renderRevisit()
    await screen.findByText(/Each one needs a decision/)
    const u = user()
    await u.click(within(card('Moved four times')).getByRole('button', { name: 'Break it down' }))

    // The sheet's submit is the last "Break it down" button on the page.
    const sheetSubmit = screen
      .getAllByRole('button', { name: 'Break it down', hidden: true })
      .at(-1)
    expect(sheetSubmit).toBeDisabled()

    await u.type(screen.getByLabelText('Step 1'), 'Write the outline')
    await u.type(screen.getByLabelText('Step 2'), 'Draft the intro')
    await u.click(screen.getByRole('radio', { name: 'Tomorrow', hidden: true }))
    await u.click(sheetSubmit as HTMLElement)

    const writes = lastMutate().writes
    const created = writes.filter((w) => w.table === 'items' && w.fields.kind === 'task')
    expect(created.map((w) => w.fields.title)).toEqual(['Write the outline', 'Draft the intro'])
    expect(writes.at(-1)).toEqual({
      table: 'items',
      key: { id: 'Moved four times' },
      fields: { status: 'archived' },
    })
    expect(
      writes.find((w) => w.table === 'task_fields' && w.key.item_id === created[0].key.id)?.fields,
    ).toEqual({ scheduled_for: addLocalDays(TODAY, 1) })
    expect(screen.getByText('Split into 2 steps')).toBeInTheDocument()

    await u.click(screen.getByRole('button', { name: 'Undo' }))
    const undo = lastMutate().writes
    expect(undo).toContainEqual({
      table: 'items',
      key: { id: 'Moved four times' },
      fields: { status: 'active' },
    })
    expect(undo.filter((w) => w.table === 'items' && 'deleted_at' in w.fields)).toHaveLength(2)
  })

  it('offers more steps, up to the limit', async () => {
    serve({ tasks: SLIPPING })
    renderRevisit()
    await screen.findByText(/Each one needs a decision/)
    const u = user()
    await u.click(within(card('Moved once')).getByRole('button', { name: 'Break it down' }))
    await u.click(screen.getByRole('button', { name: 'Add another step', hidden: true }))
    expect(screen.getByLabelText('Step 3')).toBeInTheDocument()
  })
})

describe('RevisitRoute: let it go', () => {
  it('someday or delete, each undoable', async () => {
    serve({ tasks: SLIPPING })
    renderRevisit()
    await screen.findByText(/Each one needs a decision/)
    const u = user()

    await u.click(within(card('Moved once')).getByRole('button', { name: 'Let it go' }))
    await u.click(screen.getByRole('button', { name: 'Move to someday', hidden: true }))
    expect(lastMutate().writes).toEqual([
      { table: 'task_fields', key: { item_id: 'Moved once' }, fields: { someday: 1 } },
    ])
    await u.click(screen.getByRole('button', { name: 'Undo' }))
    expect(lastMutate().writes).toEqual([
      { table: 'task_fields', key: { item_id: 'Moved once' }, fields: { someday: 0 } },
    ])

    await u.click(within(card('Left alone')).getByRole('button', { name: 'Let it go' }))
    await u.click(screen.getByRole('button', { name: 'Delete', hidden: true }))
    expect(lastMutate().writes[0]).toMatchObject({
      table: 'items',
      key: { id: 'Left alone' },
    })
    expect(screen.getByText('Deleted')).toBeInTheDocument()
  })
})
