import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import App from './App'

describe('App', () => {
  it('renders the Life Helper heading', () => {
    render(<App />)
    expect(screen.getByRole('heading', { name: 'Life Helper' })).toBeInTheDocument()
  })
})
