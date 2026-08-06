import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ListRow } from './ListRow'

describe('ListRow', () => {
  it('renders as a button and fires onClick when interactive (the default)', async () => {
    const onClick = vi.fn()
    render(<ListRow title="Buy milk" subtitle="Inbox" onClick={onClick} />)
    await userEvent.click(screen.getByRole('button', { name: /Buy milk/ }))
    expect(onClick).toHaveBeenCalledTimes(1)
  })

  it('renders as a non-interactive div, out of tab order, when interactive is false', () => {
    render(<ListRow title="Buy milk" interactive={false} />)
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
    expect(screen.getByText('Buy milk')).toBeInTheDocument()
  })
})
