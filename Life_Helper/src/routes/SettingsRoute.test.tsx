import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { CONNECTION_KEY, readCache, writeCache } from '../calendar/calendarStore'
import { CAPACITY_SETTINGS_KEY } from '../calendar/capacitySettings'
import { RouterProvider } from '../ui/router'
import { SettingsRoute } from './SettingsRoute'

const KEY = 'k'.repeat(43)

function renderSettings() {
  return render(
    <RouterProvider>
      <SettingsRoute />
    </RouterProvider>,
  )
}

function stored(key: string): unknown {
  const raw = window.localStorage.getItem(key)
  return raw === null ? null : JSON.parse(raw)
}

let fetchMock: ReturnType<typeof vi.fn<typeof fetch>>

beforeEach(() => {
  fetchMock = vi.fn<typeof fetch>(() =>
    Promise.resolve(
      new Response(JSON.stringify({ events: [], fetchedAt: Date.now() }), { status: 200 }),
    ),
  )
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('SettingsRoute: calendar connection', () => {
  it('connecting stores the Worker origin and key on this device, and checks it', async () => {
    const user = userEvent.setup({ delay: null })
    renderSettings()
    await user.type(
      screen.getByLabelText('Worker address'),
      'https://life-helper-edge.me.workers.dev/some/path',
    )
    await user.type(screen.getByLabelText('Device key'), `  ${KEY}  `)
    await user.click(screen.getByRole('button', { name: 'Connect' }))

    expect(stored(CONNECTION_KEY)).toEqual({
      edgeUrl: 'https://life-helper-edge.me.workers.dev',
      deviceKey: KEY,
    })
    expect(await screen.findByText(/^Working\. Last updated/)).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('refuses a plain-http Worker address — the key would travel in the clear', async () => {
    const user = userEvent.setup({ delay: null })
    renderSettings()
    await user.type(screen.getByLabelText('Worker address'), 'http://edge.example.com')
    await user.type(screen.getByLabelText('Device key'), KEY)
    await user.click(screen.getByRole('button', { name: 'Connect' }))
    expect(screen.getByRole('alert')).toHaveTextContent('https://')
    expect(stored(CONNECTION_KEY)).toBeNull()
  })

  it('allows plain http only for a local `wrangler dev` Worker', async () => {
    const user = userEvent.setup({ delay: null })
    renderSettings()
    await user.type(screen.getByLabelText('Worker address'), 'http://localhost:8787')
    await user.type(screen.getByLabelText('Device key'), KEY)
    await user.click(screen.getByRole('button', { name: 'Connect' }))
    expect(stored(CONNECTION_KEY)).toMatchObject({ edgeUrl: 'http://localhost:8787' })
  })

  it('says plainly when the Worker rejects the key', async () => {
    fetchMock.mockImplementation(() =>
      Promise.resolve(new Response(JSON.stringify({ error: 'unauthorized' }), { status: 401 })),
    )
    const user = userEvent.setup({ delay: null })
    renderSettings()
    await user.type(screen.getByLabelText('Worker address'), 'https://edge.example.workers.dev')
    await user.type(screen.getByLabelText('Device key'), 'wrong')
    await user.click(screen.getByRole('button', { name: 'Connect' }))
    expect(await screen.findByText("The Worker didn't accept this device key.")).toBeInTheDocument()
  })

  it('disconnecting forgets the connection and the cached calendar', async () => {
    window.localStorage.setItem(
      CONNECTION_KEY,
      JSON.stringify({ edgeUrl: 'https://edge.example.workers.dev', deviceKey: KEY }),
    )
    writeCache({ ...readCache(), fetchedAt: Date.now(), lastAttemptAt: Date.now() })
    const user = userEvent.setup({ delay: null })
    renderSettings()
    await user.click(screen.getByRole('button', { name: 'Disconnect this device' }))
    expect(stored(CONNECTION_KEY)).toBeNull()
    expect(readCache().fetchedAt).toBeNull()
    expect(screen.getByText('Not connected on this device.')).toBeInTheDocument()
  })
})

describe('SettingsRoute: free time and reminder', () => {
  it('stores waking hours and the buffer on this device', () => {
    renderSettings()
    fireEvent.change(screen.getByLabelText('Day starts'), { target: { value: '06:30' } })
    fireEvent.change(screen.getByLabelText('Buffer (minutes)'), { target: { value: '90' } })
    expect(stored(CAPACITY_SETTINGS_KEY)).toEqual({
      wakeStart: '06:30',
      wakeEnd: '23:00',
      bufferMinutes: 90,
    })
    expect(screen.getByText(/Buffer: 1h 30m over a full day/)).toBeInTheDocument()
  })

  it('the evening reminder time is the same one the shutdown page uses', () => {
    renderSettings()
    fireEvent.change(screen.getByLabelText('Remind me from'), { target: { value: '21:15' } })
    expect(window.localStorage.getItem('life-helper-shutdown-time')).toBe('21:15')
  })
})

describe('SettingsRoute: tools', () => {
  it('links to the gallery, which no longer has a tab of its own', () => {
    renderSettings()
    expect(screen.getByRole('link', { name: 'Open the gallery' })).toHaveAttribute(
      'href',
      '/gallery',
    )
  })
})
