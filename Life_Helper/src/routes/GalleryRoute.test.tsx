import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReplayComparisonResult } from '../db/ops'

const { verifyReplayMock } = vi.hoisted(() => ({ verifyReplayMock: vi.fn() }))

vi.mock('../db/client', () => ({
  dbClient: {
    verifyReplay: () => verifyReplayMock() as Promise<ReplayComparisonResult>,
  },
}))

const { GalleryRoute } = await import('./GalleryRoute')

const OK_RESULT: ReplayComparisonResult = {
  ok: true,
  tables: [
    { table: 'items', liveRowCount: 3, replayedRowCount: 3, matches: true },
    { table: 'task_fields', liveRowCount: 3, replayedRowCount: 3, matches: true },
  ],
}

const MISMATCH_RESULT: ReplayComparisonResult = {
  ok: false,
  tables: [
    { table: 'items', liveRowCount: 3, replayedRowCount: 2, matches: false },
    { table: 'task_fields', liveRowCount: 3, replayedRowCount: 3, matches: true },
  ],
}

beforeEach(() => {
  verifyReplayMock.mockReset()
})

describe('GalleryRoute: data integrity check', () => {
  it('runs verifyReplay() and renders a pass result', async () => {
    verifyReplayMock.mockResolvedValue(OK_RESULT)
    const user = userEvent.setup({ delay: null })
    render(<GalleryRoute />)

    await user.click(screen.getByRole('button', { name: 'Run ops replay verification' }))

    expect(verifyReplayMock).toHaveBeenCalledTimes(1)
    expect(
      await screen.findByText('All tables match. Record this result in docs/usage_log.md.'),
    ).toBeInTheDocument()
    const itemsRow = screen.getByText('items').closest('tr')
    const taskFieldsRow = screen.getByText('task_fields').closest('tr')
    expect(itemsRow).toHaveTextContent('pass')
    expect(taskFieldsRow).toHaveTextContent('pass')
  })

  it('renders a mismatch result without claiming the gate passed', async () => {
    verifyReplayMock.mockResolvedValue(MISMATCH_RESULT)
    const user = userEvent.setup({ delay: null })
    render(<GalleryRoute />)

    await user.click(screen.getByRole('button', { name: 'Run ops replay verification' }))

    expect(await screen.findByText('FAIL')).toBeInTheDocument()
    expect(
      screen.getByText(/Mismatch found — do not record the gate as passed/),
    ).toBeInTheDocument()
  })

  it('shows an error message if verifyReplay() rejects', async () => {
    verifyReplayMock.mockRejectedValue(new Error('worker not ready'))
    const user = userEvent.setup({ delay: null })
    render(<GalleryRoute />)

    await user.click(screen.getByRole('button', { name: 'Run ops replay verification' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('worker not ready')
  })
})
