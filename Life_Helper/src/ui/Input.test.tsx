import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Input } from './Input'

describe('Input', () => {
  it('associates the label with the input', () => {
    render(<Input label="Title" />)
    expect(screen.getByLabelText('Title')).toBeInTheDocument()
  })

  it('marks the input invalid and describes the error when one is given', () => {
    render(<Input label="Title" error="Title is required" />)
    const input = screen.getByLabelText('Title')
    expect(input).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByText('Title is required')).toBeInTheDocument()
    expect(input).toHaveAccessibleDescription('Title is required')
  })

  it('has no aria-invalid when there is no error', () => {
    render(<Input label="Title" />)
    expect(screen.getByLabelText('Title')).not.toHaveAttribute('aria-invalid')
  })
})
