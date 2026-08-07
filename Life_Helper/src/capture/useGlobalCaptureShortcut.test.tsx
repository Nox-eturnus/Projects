import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { RouterProvider, useRouter } from '../ui/router'
import {
  CAPTURE_PATH,
  FOCUS_CAPTURE_EVENT,
  useGlobalCaptureShortcut,
} from './useGlobalCaptureShortcut'

function Harness() {
  useGlobalCaptureShortcut()
  const { path } = useRouter()
  return <div data-testid="path">{path}</div>
}

function renderHarness() {
  return render(
    <RouterProvider>
      <Harness />
    </RouterProvider>,
  )
}

describe('useGlobalCaptureShortcut', () => {
  beforeEach(() => {
    window.history.pushState(null, '', '/')
  })

  afterEach(() => {
    window.history.pushState(null, '', '/')
  })

  it('navigates to /capture on Ctrl+K from elsewhere in the app', async () => {
    renderHarness()
    expect(screen.getByTestId('path')).toHaveTextContent('/')

    await userEvent.keyboard('{Control>}k{/Control}')

    expect(screen.getByTestId('path')).toHaveTextContent(CAPTURE_PATH)
  })

  it('navigates to /capture on Cmd+K (metaKey)', async () => {
    renderHarness()

    await userEvent.keyboard('{Meta>}k{/Meta}')

    expect(screen.getByTestId('path')).toHaveTextContent(CAPTURE_PATH)
  })

  it('does not navigate on a bare "k" with no modifier', async () => {
    renderHarness()

    await userEvent.keyboard('k')

    expect(screen.getByTestId('path')).toHaveTextContent('/')
  })

  it('dispatches a focus event instead of navigating when already on /capture', async () => {
    window.history.pushState(null, '', CAPTURE_PATH)
    renderHarness()
    const onFocusEvent = vi.fn()
    window.addEventListener(FOCUS_CAPTURE_EVENT, onFocusEvent)

    await userEvent.keyboard('{Control>}k{/Control}')

    expect(onFocusEvent).toHaveBeenCalledTimes(1)
    expect(screen.getByTestId('path')).toHaveTextContent(CAPTURE_PATH)
    window.removeEventListener(FOCUS_CAPTURE_EVENT, onFocusEvent)
  })
})
