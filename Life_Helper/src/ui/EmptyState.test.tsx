import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { EmptyState } from './EmptyState'

describe('EmptyState', () => {
  it('shows the message and a single action', async () => {
    const onAction = vi.fn()
    render(
      <EmptyState message="Nothing here yet." actionLabel="Capture a task" onAction={onAction} />,
    )
    expect(screen.getByText('Nothing here yet.')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Capture a task' }))
    expect(onAction).toHaveBeenCalledTimes(1)
  })
})
