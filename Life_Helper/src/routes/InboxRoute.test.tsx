import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { RouterProvider } from '../ui/router'

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

const { InboxRoute } = await import('./InboxRoute')

const THREE_DAYS_MS = 3 * 24 * 60 * 60 * 1000

function renderInbox() {
  return render(
    <RouterProvider>
      <InboxRoute />
    </RouterProvider>,
  )
}

beforeEach(() => {
  mutateMock.mockReset().mockResolvedValue({ touchedTables: new Set(), opsInserted: 0 })
  queryMock.mockReset().mockResolvedValue([])
  listeners.clear()
  window.history.pushState(null, '', '/inbox')
})

describe('InboxRoute', () => {
  it('empty state: no inbox items, offers to go capture something', async () => {
    renderInbox()

    expect(await screen.findByText('Inbox zero. Nothing to triage.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Start triage' })).not.toBeInTheDocument()

    await userEvent
      .setup({ delay: null })
      .click(screen.getByRole('button', { name: 'Go to Capture' }))
    expect(window.location.pathname).toBe('/capture')
  })

  it('loaded state: lists inbox items newest first and offers to start triage', async () => {
    const now = Date.now()
    queryMock.mockImplementation((sql: string) => {
      if (sql.includes('FROM items') && sql.includes('LEFT JOIN task_fields')) {
        return Promise.resolve([
          {
            id: 'a',
            title: 'Newer',
            status: 'inbox',
            created_at: now - 1000,
            scheduled_for: null,
            someday: 0,
            completed_at: null,
          },
          {
            id: 'b',
            title: 'Older',
            status: 'inbox',
            created_at: now - 2000,
            scheduled_for: null,
            someday: 0,
            completed_at: null,
          },
        ])
      }
      return Promise.resolve([])
    })
    renderInbox()

    expect(await screen.findByText('Newer')).toBeInTheDocument()
    expect(screen.getByText('Older')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Start triage' })).toBeInTheDocument()
  })

  it('cold state: most recent inbox item is 3+ days old, no guilt language', async () => {
    const now = Date.now()
    queryMock.mockImplementation((sql: string) => {
      if (sql.includes('FROM items') && sql.includes('LEFT JOIN task_fields')) {
        return Promise.resolve([
          {
            id: 'a',
            title: 'Old one',
            status: 'inbox',
            created_at: now - THREE_DAYS_MS - 1,
            scheduled_for: null,
            someday: 0,
            completed_at: null,
          },
        ])
      }
      return Promise.resolve([])
    })
    renderInbox()

    expect(await screen.findByText("Welcome back. Here's what's waiting.")).toBeInTheDocument()
    expect(screen.queryByText('Old one')).not.toBeInTheDocument()
  })

  it('starting triage shows the one-item-at-a-time view', async () => {
    queryMock.mockImplementation((sql: string) => {
      if (sql.includes('FROM items') && sql.includes('LEFT JOIN task_fields')) {
        return Promise.resolve([
          {
            id: 'a',
            title: 'Buy milk',
            status: 'inbox',
            created_at: 1000,
            scheduled_for: null,
            someday: 0,
            completed_at: null,
          },
        ])
      }
      return Promise.resolve([])
    })
    const user = userEvent.setup({ delay: null })
    renderInbox()

    await user.click(await screen.findByRole('button', { name: 'Start triage' }))

    expect(screen.getByRole('heading', { name: 'Buy milk' })).toBeInTheDocument()
    expect(screen.getByText('1 item left')).toBeInTheDocument()
  })

  it('exiting triage returns to the inbox list', async () => {
    queryMock.mockImplementation((sql: string) => {
      if (sql.includes('FROM items') && sql.includes('LEFT JOIN task_fields')) {
        return Promise.resolve([
          {
            id: 'a',
            title: 'Buy milk',
            status: 'inbox',
            created_at: 1000,
            scheduled_for: null,
            someday: 0,
            completed_at: null,
          },
        ])
      }
      return Promise.resolve([])
    })
    const user = userEvent.setup({ delay: null })
    renderInbox()

    await user.click(await screen.findByRole('button', { name: 'Start triage' }))
    await user.click(screen.getByRole('button', { name: 'Exit triage' }))

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Start triage' })).toBeInTheDocument()
    })
  })
})
