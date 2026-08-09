import { beforeEach, describe, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

const { mutateMock } = vi.hoisted(() => ({ mutateMock: vi.fn() }))

vi.mock('../db/client', () => ({
  dbClient: {
    mutate: (input: unknown) => mutateMock(input) as Promise<unknown>,
  },
}))

const { TriageView } = await import('./TriageView')
type TriageItemRow = import('./TriageView').TriageItemRow
type ProjectOption = import('./TriageView').ProjectOption

function item(overrides: Partial<TriageItemRow> = {}): TriageItemRow {
  return {
    id: 'item-1',
    title: 'Buy milk',
    status: 'inbox',
    created_at: 1000,
    scheduled_for: null,
    someday: 0,
    completed_at: null,
    ...overrides,
  }
}

function writesFor(call: unknown): { table: string; fields: Record<string, unknown> }[] {
  return (call as { writes: { table: string; fields: Record<string, unknown> }[] }).writes
}

beforeEach(() => {
  mutateMock.mockReset().mockResolvedValue({ touchedTables: new Set(), opsInserted: 0 })
})

describe('TriageView', () => {
  it('shows the current item and how many are left', () => {
    render(<TriageView items={[item(), item({ id: 'item-2' })]} projects={[]} onExit={vi.fn()} />)
    expect(screen.getByRole('heading', { name: 'Buy milk' })).toBeInTheDocument()
    expect(screen.getByText('2 items left')).toBeInTheDocument()
  })

  it('inbox zero: shows a completion message and exits on demand', async () => {
    const user = userEvent.setup({ delay: null })
    const onExit = vi.fn()
    render(<TriageView items={[]} projects={[]} onExit={onExit} />)

    expect(screen.getByText('Inbox zero. Nice work.')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Back to inbox' }))
    expect(onExit).toHaveBeenCalledTimes(1)
  })

  it('pressing T schedules the current item for today', () => {
    render(<TriageView items={[item()]} projects={[]} onExit={vi.fn()} />)

    fireEvent.keyDown(window, { key: 't' })

    expect(mutateMock).toHaveBeenCalledTimes(1)
    const [itemsWrite, taskFieldsWrite] = writesFor(mutateMock.mock.calls[0][0])
    expect(itemsWrite).toMatchObject({ table: 'items', fields: { status: 'active' } })
    expect(taskFieldsWrite).toMatchObject({ table: 'task_fields' })
    expect(typeof taskFieldsWrite.fields.scheduled_for).toBe('number')
  })

  it('pressing Enter marks the item done', () => {
    render(<TriageView items={[item()]} projects={[]} onExit={vi.fn()} />)

    fireEvent.keyDown(window, { key: 'Enter' })

    const [, taskFieldsWrite] = writesFor(mutateMock.mock.calls[0][0])
    expect(taskFieldsWrite.fields).toHaveProperty('completed_at')
  })

  it('pressing Backspace deletes (tombstones) the item', () => {
    render(<TriageView items={[item()]} projects={[]} onExit={vi.fn()} />)

    fireEvent.keyDown(window, { key: 'Backspace' })

    expect(writesFor(mutateMock.mock.calls[0][0])).toEqual([
      {
        table: 'items',
        key: { id: 'item-1' },
        fields: { deleted_at: expect.any(Number) as number },
      },
    ])
  })

  it('pressing N converts to a note, R converts to a routine, S sets someday', () => {
    render(<TriageView items={[item()]} projects={[]} onExit={vi.fn()} />)

    fireEvent.keyDown(window, { key: 'n' })
    expect(writesFor(mutateMock.mock.calls[0][0])[0]).toMatchObject({ fields: { kind: 'note' } })

    fireEvent.keyDown(window, { key: 'r' })
    expect(writesFor(mutateMock.mock.calls[1][0])[0]).toMatchObject({ fields: { kind: 'routine' } })

    fireEvent.keyDown(window, { key: 's' })
    const [, taskFieldsWrite] = writesFor(mutateMock.mock.calls[2][0])
    expect(taskFieldsWrite.fields).toMatchObject({ someday: 1 })
  })

  it('shows an undo toast after an action, and Undo reverts it', async () => {
    const user = userEvent.setup({ delay: null })
    render(<TriageView items={[item()]} projects={[]} onExit={vi.fn()} />)

    fireEvent.keyDown(window, { key: 't' })
    expect(await screen.findByText('Scheduled for today')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Undo' }))

    expect(mutateMock).toHaveBeenCalledTimes(2)
    const [itemsWrite, taskFieldsWrite] = writesFor(mutateMock.mock.calls[1][0])
    expect(itemsWrite).toMatchObject({ fields: { status: 'inbox' } })
    expect(taskFieldsWrite).toMatchObject({ fields: { scheduled_for: null } })
    expect(screen.queryByText('Scheduled for today')).not.toBeInTheDocument()
  })

  it('the undo toast disappears on its own after 10 seconds', () => {
    vi.useFakeTimers()
    try {
      render(<TriageView items={[item()]} projects={[]} onExit={vi.fn()} />)
      fireEvent.keyDown(window, { key: 't' })
      expect(screen.getByText('Scheduled for today')).toBeInTheDocument()

      act(() => {
        vi.advanceTimersByTime(10_000)
      })

      expect(screen.queryByText('Scheduled for today')).not.toBeInTheDocument()
    } finally {
      vi.useRealTimers()
    }
  })

  it('a fresh action replaces the previous undo toast', () => {
    render(
      <TriageView
        items={[item(), item({ id: 'item-2', title: 'Walk the dog' })]}
        projects={[]}
        onExit={vi.fn()}
      />,
    )

    fireEvent.keyDown(window, { key: 't' })
    expect(screen.getByText('Scheduled for today')).toBeInTheDocument()

    fireEvent.keyDown(window, { key: 'Backspace' })
    expect(screen.queryByText('Scheduled for today')).not.toBeInTheDocument()
    expect(screen.getByText('Deleted')).toBeInTheDocument()
  })

  it('date sheet: schedules for the chosen date and suppresses keyboard shortcuts while open', async () => {
    const user = userEvent.setup({ delay: null })
    render(<TriageView items={[item()]} projects={[]} onExit={vi.fn()} />)

    await user.click(screen.getByRole('button', { name: /^Date/ }))
    // A global 'n' while the sheet is open must not fire convertToNote.
    fireEvent.keyDown(window, { key: 'n' })
    expect(mutateMock).not.toHaveBeenCalled()

    fireEvent.change(screen.getByLabelText('Date'), { target: { value: '2030-01-15' } })
    await user.click(screen.getByRole('button', { name: 'Set date', hidden: true }))

    expect(mutateMock).toHaveBeenCalledTimes(1)
    const [, taskFieldsWrite] = writesFor(mutateMock.mock.calls[0][0])
    expect(taskFieldsWrite.fields.scheduled_for).toBe(new Date(2030, 0, 15).getTime())
  })

  it('project sheet: shows "No projects yet." when there are none', async () => {
    const user = userEvent.setup({ delay: null })
    render(<TriageView items={[item()]} projects={[]} onExit={vi.fn()} />)

    await user.click(screen.getByRole('button', { name: /^Project/ }))

    expect(screen.getByText('No projects yet.')).toBeInTheDocument()
  })

  it('project sheet: filing to a project links it and closes the sheet', async () => {
    const user = userEvent.setup({ delay: null })
    const projects: ProjectOption[] = [{ id: 'project-1', title: 'Website' }]
    render(<TriageView items={[item()]} projects={projects} onExit={vi.fn()} />)

    await user.click(screen.getByRole('button', { name: /^Project/ }))
    await user.click(screen.getByRole('button', { name: 'Website', hidden: true }))

    expect(writesFor(mutateMock.mock.calls[0][0])).toContainEqual({
      table: 'links',
      key: { from_id: 'item-1', to_id: 'project-1', rel: 'project' },
      fields: { created_at: expect.any(Number) as number },
    })
    expect(screen.getByText('Filed to Website')).toBeInTheDocument()
  })

  it('swipe right on the card marks the item done', () => {
    render(<TriageView items={[item()]} projects={[]} onExit={vi.fn()} />)
    const card = screen.getByRole('heading', { name: 'Buy milk' }).parentElement
    if (!card) throw new Error('expected the card element to exist')

    fireEvent.pointerDown(card, { clientX: 0 })
    fireEvent.pointerUp(card, { clientX: 200 })

    const [, taskFieldsWrite] = writesFor(mutateMock.mock.calls[0][0])
    expect(taskFieldsWrite.fields).toHaveProperty('completed_at')
  })

  it('swipe left on the card sets someday', () => {
    render(<TriageView items={[item()]} projects={[]} onExit={vi.fn()} />)
    const card = screen.getByRole('heading', { name: 'Buy milk' }).parentElement
    if (!card) throw new Error('expected the card element to exist')

    fireEvent.pointerDown(card, { clientX: 200 })
    fireEvent.pointerUp(card, { clientX: 0 })

    const [, taskFieldsWrite] = writesFor(mutateMock.mock.calls[0][0])
    expect(taskFieldsWrite.fields).toMatchObject({ someday: 1 })
  })

  it('a small drag below the swipe threshold does nothing', () => {
    render(<TriageView items={[item()]} projects={[]} onExit={vi.fn()} />)
    const card = screen.getByRole('heading', { name: 'Buy milk' }).parentElement
    if (!card) throw new Error('expected the card element to exist')

    fireEvent.pointerDown(card, { clientX: 0 })
    fireEvent.pointerUp(card, { clientX: 20 })

    expect(mutateMock).not.toHaveBeenCalled()
  })
})
