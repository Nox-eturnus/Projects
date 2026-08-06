import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { computeViewState, ThreeStateView } from './ThreeStateView'

describe('ThreeStateView', () => {
  const props = {
    empty: <p>Empty content</p>,
    cold: <p>Cold content</p>,
    loaded: <p>Loaded content</p>,
  }

  it('renders only the matching state', () => {
    const { rerender } = render(<ThreeStateView state="empty" {...props} />)
    expect(screen.getByText('Empty content')).toBeInTheDocument()
    expect(screen.queryByText('Cold content')).not.toBeInTheDocument()
    expect(screen.queryByText('Loaded content')).not.toBeInTheDocument()

    rerender(<ThreeStateView state="cold" {...props} />)
    expect(screen.getByText('Cold content')).toBeInTheDocument()

    rerender(<ThreeStateView state="loaded" {...props} />)
    expect(screen.getByText('Loaded content')).toBeInTheDocument()
  })
})

describe('computeViewState', () => {
  const DAY_MS = 24 * 60 * 60 * 1000
  const now = 1_700_000_000_000

  it('is empty when there is no data, regardless of last activity', () => {
    expect(computeViewState(true, now, now)).toBe('empty')
    expect(computeViewState(true, null, now)).toBe('empty')
  })

  it('is loaded when active within the last 3 days', () => {
    expect(computeViewState(false, now - 2 * DAY_MS, now)).toBe('loaded')
  })

  it('is loaded when there is no absence to measure', () => {
    expect(computeViewState(false, null, now)).toBe('loaded')
  })

  it('is cold at exactly 3 days of absence and beyond', () => {
    expect(computeViewState(false, now - 3 * DAY_MS, now)).toBe('cold')
    expect(computeViewState(false, now - 10 * DAY_MS, now)).toBe('cold')
  })
})
