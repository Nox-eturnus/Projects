import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { FOCUS_CAPTURE_EVENT } from '../capture/useGlobalCaptureShortcut'

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

const { CaptureRoute } = await import('./CaptureRoute')

const THREE_DAYS_MS = 3 * 24 * 60 * 60 * 1000

function notifyItemsChanged(): void {
  for (const listener of listeners) listener(['items'])
}

beforeEach(() => {
  mutateMock.mockReset().mockResolvedValue({ touchedTables: new Set(['items']), opsInserted: 1 })
  queryMock.mockReset().mockResolvedValue([])
  listeners.clear()
})

describe('CaptureRoute', () => {
  it('auto-focuses the capture field on mount', async () => {
    render(<CaptureRoute />)
    await waitFor(() => expect(screen.getByLabelText('Capture')).toHaveFocus())
  })

  it('submits on Enter, clears the field, and keeps focus', async () => {
    const user = userEvent.setup({ delay: null })
    render(<CaptureRoute />)
    const field = screen.getByLabelText('Capture')

    await user.type(field, 'Buy milk{Enter}')

    await waitFor(() => {
      expect(mutateMock).toHaveBeenCalledTimes(1)
    })
    const call = mutateMock.mock.calls[0][0] as {
      writes: { table: string; fields: Record<string, unknown> }[]
    }
    expect(call.writes[0]).toMatchObject({
      table: 'items',
      fields: { kind: 'task', title: 'Buy milk', status: 'inbox' },
    })
    expect(call.writes[1]).toMatchObject({ table: 'task_fields' })

    await waitFor(() => expect(field).toHaveValue(''))
    expect(field).toHaveFocus()
  })

  it('inserts a newline on Shift+Enter instead of submitting', async () => {
    const user = userEvent.setup({ delay: null })
    render(<CaptureRoute />)
    const field = screen.getByLabelText('Capture')

    await user.type(field, 'line one{Shift>}{Enter}{/Shift}line two')

    expect(mutateMock).not.toHaveBeenCalled()
    expect(field).toHaveValue('line one\nline two')
  })

  it('does not write anything for blank input', async () => {
    const user = userEvent.setup({ delay: null })
    render(<CaptureRoute />)
    const field = screen.getByLabelText('Capture')

    await user.type(field, '   {Enter}')

    expect(mutateMock).not.toHaveBeenCalled()
  })

  it('focuses the field when the mic button is clicked', async () => {
    const user = userEvent.setup({ delay: null })
    render(<CaptureRoute />)
    const field = screen.getByLabelText('Capture')
    field.blur()
    expect(field).not.toHaveFocus()

    await user.click(screen.getByRole('button', { name: 'Dictate with the system keyboard' }))

    expect(field).toHaveFocus()
  })

  it('refocuses the field on a FOCUS_CAPTURE_EVENT', () => {
    render(<CaptureRoute />)
    const field = screen.getByLabelText('Capture')
    field.blur()
    expect(field).not.toHaveFocus()

    window.dispatchEvent(new Event(FOCUS_CAPTURE_EVENT))

    expect(field).toHaveFocus()
  })

  it('empty state: no captures yet', async () => {
    queryMock.mockResolvedValue([])
    render(<CaptureRoute />)

    expect(
      await screen.findByText(
        'Nothing captured yet. Type above and press Enter to add your first item.',
      ),
    ).toBeInTheDocument()
  })

  it('loaded state: renders recent captures', async () => {
    const now = Date.now()
    queryMock.mockResolvedValue([
      { id: 'a', title: 'Buy milk', created_at: now - 1000 },
      { id: 'b', title: 'Walk the dog', created_at: now - 2000 },
    ])
    render(<CaptureRoute />)

    expect(await screen.findByText('Buy milk')).toBeInTheDocument()
    expect(screen.getByText('Walk the dog')).toBeInTheDocument()
  })

  it('cold state: most recent capture is 3+ days old, no guilt language', async () => {
    const now = Date.now()
    queryMock.mockResolvedValue([
      { id: 'a', title: 'Old one', created_at: now - THREE_DAYS_MS - 1 },
    ])
    render(<CaptureRoute />)

    expect(
      await screen.findByText('Welcome back. New captures will show up here.'),
    ).toBeInTheDocument()
    expect(screen.queryByText('Old one')).not.toBeInTheDocument()
  })

  it('re-queries recent captures when a mutate() touches items', async () => {
    render(<CaptureRoute />)
    await waitFor(() => {
      expect(queryMock).toHaveBeenCalledTimes(1)
    })

    notifyItemsChanged()

    await waitFor(() => {
      expect(queryMock).toHaveBeenCalledTimes(2)
    })
  })

  describe('parsed chips (Part B2)', () => {
    it('renders a removable chip for a recognized token as the user types', async () => {
      const user = userEvent.setup({ delay: null })
      render(<CaptureRoute />)

      await user.type(screen.getByLabelText('Capture'), 'Buy milk @Rahul')

      expect(screen.getByRole('button', { name: 'Remove @Rahul' })).toBeInTheDocument()
    })

    it('an accepted date token is stripped from the title and applied to scheduled_for', async () => {
      const user = userEvent.setup({ delay: null })
      render(<CaptureRoute />)

      await user.type(screen.getByLabelText('Capture'), 'Buy milk tomorrow{Enter}')

      await waitFor(() => {
        expect(mutateMock).toHaveBeenCalledTimes(1)
      })
      const call = mutateMock.mock.calls[0][0] as {
        writes: { table: string; fields: Record<string, unknown> }[]
      }
      expect(call.writes[0].fields.title).toBe('Buy milk')
      expect(typeof call.writes[1].fields.scheduled_for).toBe('number')
    })

    it('an accepted estimate token is stripped from the title and applied to estimate_min', async () => {
      const user = userEvent.setup({ delay: null })
      render(<CaptureRoute />)

      await user.type(screen.getByLabelText('Capture'), 'Buy milk ~45m{Enter}')

      await waitFor(() => {
        expect(mutateMock).toHaveBeenCalledTimes(1)
      })
      const call = mutateMock.mock.calls[0][0] as {
        writes: { table: string; fields: Record<string, unknown> }[]
      }
      expect(call.writes[0].fields.title).toBe('Buy milk')
      expect(call.writes[1].fields.estimate_min).toBe(45)
    })

    it('removing a date chip keeps its raw text in the title and leaves scheduled_for unset', async () => {
      const user = userEvent.setup({ delay: null })
      render(<CaptureRoute />)
      const field = screen.getByLabelText('Capture')

      await user.type(field, 'Buy milk tomorrow')
      await user.click(screen.getByRole('button', { name: 'Remove Tomorrow' }))
      await user.type(field, '{Enter}')

      await waitFor(() => {
        expect(mutateMock).toHaveBeenCalledTimes(1)
      })
      const call = mutateMock.mock.calls[0][0] as {
        writes: { table: string; fields: Record<string, unknown> }[]
      }
      expect(call.writes[0].fields.title).toBe('Buy milk tomorrow')
      expect(call.writes[1].fields.scheduled_for).toBeUndefined()
    })

    it('removing a chip does not submit or change the field value', async () => {
      const user = userEvent.setup({ delay: null })
      render(<CaptureRoute />)
      const field = screen.getByLabelText('Capture')

      await user.type(field, 'Buy milk @Rahul')
      await user.click(screen.getByRole('button', { name: 'Remove @Rahul' }))

      expect(mutateMock).not.toHaveBeenCalled()
      expect(field).toHaveValue('Buy milk @Rahul')
      expect(screen.queryByRole('button', { name: 'Remove @Rahul' })).not.toBeInTheDocument()
    })

    it('a pure date capture with nothing else falls back to the raw text as the title', async () => {
      const user = userEvent.setup({ delay: null })
      render(<CaptureRoute />)

      await user.type(screen.getByLabelText('Capture'), 'tomorrow{Enter}')

      await waitFor(() => {
        expect(mutateMock).toHaveBeenCalledTimes(1)
      })
      const call = mutateMock.mock.calls[0][0] as {
        writes: { table: string; fields: Record<string, unknown> }[]
      }
      expect(call.writes[0].fields.title).toBe('tomorrow')
    })

    it('chips clear after a successful submit', async () => {
      const user = userEvent.setup({ delay: null })
      render(<CaptureRoute />)
      const field = screen.getByLabelText('Capture')

      await user.type(field, 'Buy milk @Rahul{Enter}')

      await waitFor(() => {
        expect(screen.queryByRole('button', { name: 'Remove @Rahul' })).not.toBeInTheDocument()
      })
    })
  })
})
