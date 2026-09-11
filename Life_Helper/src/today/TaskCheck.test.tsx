import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { TaskCheck } from './TaskCheck'

describe('TaskCheck', () => {
  it('is a labelled checkbox that reports the new state', async () => {
    const onToggle = vi.fn()
    render(<TaskCheck title="Water plants" detail="6:00 PM" done={false} onToggle={onToggle} />)
    await userEvent
      .setup({ delay: null })
      .click(screen.getByRole('checkbox', { name: /Water plants/ }))
    expect(onToggle).toHaveBeenCalledWith(true)
  })

  it('shows the tick immediately, before the database catches up, then follows the database', async () => {
    const user = userEvent.setup({ delay: null })
    const { rerender } = render(<TaskCheck title="A" done={false} onToggle={vi.fn()} />)
    const box = screen.getByRole('checkbox', { name: 'A' })

    await user.click(box)
    expect(box).toBeChecked() // still done={false} from the database

    rerender(<TaskCheck title="A" done onToggle={vi.fn()} />)
    expect(box).toBeChecked()

    // Later un-done from elsewhere (an undo, another tab): the database wins.
    rerender(<TaskCheck title="A" done={false} onToggle={vi.fn()} />)
    expect(box).not.toBeChecked()
  })
})
