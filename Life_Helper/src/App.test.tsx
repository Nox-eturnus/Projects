import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import App from './App'

describe('App', () => {
  it('opens on Today inside the shell', () => {
    window.history.pushState(null, '', '/')
    render(<App />)
    expect(screen.getByText('Life Helper')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Today', level: 1 })).toBeInTheDocument()
  })
})
