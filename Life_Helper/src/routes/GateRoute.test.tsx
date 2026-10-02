import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { CONNECTION_KEY } from '../calendar/calendarStore'
import { CALENDAR_HEALTH_KEY, COLD_STARTS_KEY, OPEN_DAYS_KEY } from '../gate/gateLog'
import { addLocalDays, localDayKey, startOfLocalDay } from '../scheduling/localDay'
import { RouterProvider } from '../ui/router'

const { queryMock } = vi.hoisted(() => ({ queryMock: vi.fn() }))

vi.mock('../db/client', () => ({
  dbClient: {
    mutate: vi.fn(),
    query: (sql: string, params: unknown[]) => queryMock(sql, params) as Promise<unknown>,
    getDeviceId: () => Promise.resolve('device-1'),
    subscribe: () => () => undefined,
  },
}))

const { GateRoute } = await import('./GateRoute')

const TODAY = startOfLocalDay(Date.now())
const day = (offset: number) => addLocalDays(TODAY, offset)
const ANDROID_UA = 'Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 Chrome/131 Mobile'

function serve(data: {
  activity?: number[]
  shutdowns?: string[]
  sweeps?: { swept_at: number; item_count: number }[]
}) {
  queryMock.mockImplementation((sql: string) => {
    if (sql.includes('UNION ALL'))
      return Promise.resolve((data.activity ?? []).map((at) => ({ at })))
    if (sql.includes('FROM day_plans')) {
      return Promise.resolve((data.shutdowns ?? []).map((d) => ({ day: d })))
    }
    if (sql.includes('FROM amnesty_sweeps')) return Promise.resolve(data.sweeps ?? [])
    return Promise.resolve([])
  })
}

function renderGate() {
  return render(
    <RouterProvider>
      <GateRoute />
    </RouterProvider>,
  )
}

beforeEach(() => {
  queryMock.mockReset()
  window.localStorage.clear()
  vi.spyOn(navigator, 'userAgent', 'get').mockReturnValue(ANDROID_UA)
})

describe('GateRoute', () => {
  it('nothing recorded yet: every condition says what is still missing', async () => {
    serve({})
    renderGate()
    expect(await screen.findByText('Not all conditions pass yet.')).toBeInTheDocument()
    expect(screen.getByText('0 of 3 Android cold starts recorded so far')).toBeInTheDocument()
    expect(screen.getByText('not connected on this device')).toBeInTheDocument()
    expect(screen.getByText('0 of the last 7 days (needs 5)')).toBeInTheDocument()
    expect(screen.getByText('no fresh start kept yet')).toBeInTheDocument()
  })

  it('everything met: all five pass, and the report says so', async () => {
    const fourteenDays = Array.from({ length: 14 }, (_, i) => day(-i) + 60_000)
    serve({
      activity: fourteenDays,
      shutdowns: [0, -1, -2, -3, -4].map((i) => localDayKey(day(i))),
      sweeps: [{ swept_at: day(-5), item_count: 6 }],
    })
    window.localStorage.setItem(
      COLD_STARTS_KEY,
      JSON.stringify([700, 820, 950].map((ms, i) => ({ at: i, ms, android: true }))),
    )
    window.localStorage.setItem(
      CALENDAR_HEALTH_KEY,
      JSON.stringify({ days: {}, firstOkAt: day(-8), lastOkAt: day(0), connectionSavedAt: null }),
    )
    window.localStorage.setItem(
      CONNECTION_KEY,
      JSON.stringify({ edgeUrl: 'https://x.example', deviceKey: 'k'.repeat(43) }),
    )
    window.localStorage.setItem(OPEN_DAYS_KEY, JSON.stringify([localDayKey(TODAY)]))
    renderGate()

    expect(
      await screen.findByText(
        'All five conditions pass. Record the report in docs/usage_log.md to close the gate.',
      ),
    ).toBeInTheDocument()
    // The conditions list (the report below repeats the same evidence).
    const conditions = within(screen.getAllByRole('list')[0])
    expect(conditions.getAllByText(/^— passes$/)).toHaveLength(5)
    expect(conditions.getByText(/median 820ms over 3 Android cold starts/)).toBeInTheDocument()
    expect(
      conditions.getByText(
        /14 consecutive days with something captured or completed, on this phone/,
      ),
    ).toBeInTheDocument()

    const report = screen.getByText(/^Today gate report/)
    expect(report.textContent).toContain('All five conditions pass.')
    expect(report.textContent).toMatch(/1\. PASS/)
  })

  it('lists the last 21 days, newest first, with what happened on each', async () => {
    serve({ activity: [day(0) + 1, day(0) + 2], shutdowns: [localDayKey(day(-1))] })
    window.localStorage.setItem(OPEN_DAYS_KEY, JSON.stringify([localDayKey(day(0))]))
    renderGate()
    await screen.findByText('Not all conditions pass yet.')
    const rows = screen.getAllByRole('row').slice(1)
    expect(rows).toHaveLength(21)
    expect(rows[0].textContent).toBe(`${localDayKey(day(0))}yes2——`)
    expect(rows[1].textContent).toBe(`${localDayKey(day(-1))}—0done—`)
  })

  it('copies the report for the usage log', async () => {
    serve({})
    const user = userEvent.setup({ delay: null })
    const writeText = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue()
    renderGate()
    await user.click(await screen.findByRole('button', { name: 'Copy report' }))
    expect(writeText).toHaveBeenCalledWith(expect.stringMatching(/^Today gate report — /))
    expect(await screen.findByRole('button', { name: 'Copied' })).toBeInTheDocument()
  })
})
