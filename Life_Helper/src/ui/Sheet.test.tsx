import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Sheet } from './Sheet'

// jsdom has no HTMLDialogElement.showModal at all (see Sheet.tsx), so the
// `open` attribute this component relies on for visibility never gets set
// here the way a real browser would set it. Queries below pass `hidden: true`
// to look past that jsdom gap rather than to assert anything about a11y.
describe('Sheet', () => {
  it('renders its title and children', () => {
    render(
      <Sheet open title="Move to project" onClose={vi.fn()}>
        <p>Pick a destination</p>
      </Sheet>,
    )
    expect(
      screen.getByRole('heading', { name: 'Move to project', hidden: true }),
    ).toBeInTheDocument()
    expect(screen.getByText('Pick a destination')).toBeInTheDocument()
  })

  it('calls onClose when the close button is clicked', async () => {
    const onClose = vi.fn()
    render(
      <Sheet open title="Move to project" onClose={onClose}>
        <p>Pick a destination</p>
      </Sheet>,
    )
    await userEvent.click(screen.getByRole('button', { name: 'Close', hidden: true }))
    expect(onClose).toHaveBeenCalledTimes(1)
  })
})
