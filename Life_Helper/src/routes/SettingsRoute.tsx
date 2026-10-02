import { useState, type SyntheticEvent } from 'react'
import { MAX_THRESHOLD_DAYS, MIN_THRESHOLD_DAYS, useThresholdDays } from '../amnesty/amnesty.js'
import { isValidTime, formatMinutes } from '../calendar/capacity.js'
import { useCapacitySettings } from '../calendar/capacitySettings.js'
import { saveConnection } from '../calendar/calendarStore.js'
import { useCalendar } from '../calendar/useCalendar.js'
import { formatSince } from '../today/labels.js'
import { useShutdownTime } from '../today/useShutdownReminder.js'
import { Button } from '../ui/Button.js'
import { Link } from '../ui/router.js'
import styles from './SettingsRoute.module.css'

function calendarStatus(calendar: ReturnType<typeof useCalendar>, now: number): string {
  if (!calendar.connected) return 'Not connected on this device.'
  if (calendar.refreshing) return 'Checking…'
  const { problem, fetchedAt } = calendar.cache
  switch (problem) {
    case 'unauthorized':
      return "The Worker didn't accept this device key."
    case 'reconnect_required':
      return 'Google needs reconnecting: run pnpm calendar:connect on your computer.'
    case 'not_configured':
      return 'The Worker is missing a secret — finish its setup.'
    case 'offline':
      return "Couldn't reach the Worker. Check the URL, or your connection."
    case 'upstream_error':
      return "The Worker couldn't reach Google just now."
    case null:
      return fetchedAt === null
        ? 'Connected — not loaded yet.'
        : `Working. Last updated ${formatSince(fetchedAt, now)}.`
  }
}

/**
 * Per-device settings (Part C3). Everything here lives in this device's
 * localStorage and nowhere else: the calendar connection (the Worker's URL
 * and this device's key for it — never a Google token), how capacity is
 * worked out, and when the evening shutdown reminder starts.
 */
export function SettingsRoute() {
  const calendar = useCalendar()
  const [capacity, setCapacity] = useCapacitySettings()
  const [shutdownTime, setShutdownTime] = useShutdownTime()
  const [thresholdDays, setThresholdDays] = useThresholdDays()
  // What's typed, so "45" can pass through "4" (below the minimum) on the
  // way; it's stored once it's a valid number of days, and snaps back to
  // the stored value on blur if it never became one.
  const [thresholdDraft, setThresholdDraft] = useState<string | null>(null)
  const [edgeUrl, setEdgeUrl] = useState(calendar.connection.edgeUrl)
  const [deviceKey, setDeviceKey] = useState(calendar.connection.deviceKey)
  const [urlError, setUrlError] = useState<string | null>(null)
  const [checkedAt, setCheckedAt] = useState(() => Date.now())

  function connect(event: SyntheticEvent<HTMLFormElement>): void {
    event.preventDefault()
    let url: URL
    try {
      url = new URL(edgeUrl.trim())
    } catch {
      setUrlError('That doesn’t look like a URL — it starts with https://.')
      return
    }
    // The device key travels as a bearer token: only ever over HTTPS, except
    // to a Worker running locally under `wrangler dev`.
    const local = url.hostname === 'localhost' || url.hostname === '127.0.0.1'
    if (url.protocol !== 'https:' && !local) {
      setUrlError('Use the Worker’s https:// address.')
      return
    }
    setUrlError(null)
    saveConnection({ edgeUrl: url.origin, deviceKey: deviceKey.trim() })
    setCheckedAt(Date.now())
  }

  function disconnect(): void {
    saveConnection(undefined)
    setEdgeUrl('')
    setDeviceKey('')
  }

  return (
    <div className={styles.settings}>
      <h1 className={styles.pageTitle}>Settings</h1>
      <p className={styles.lede}>These apply to this device only.</p>

      <section className={styles.section} aria-labelledby="calendar-settings">
        <h2 id="calendar-settings" className={styles.sectionTitle}>
          Calendar
        </h2>
        <p className={styles.help}>
          Today reads your Google Calendar through your own Cloudflare Worker, read-only. Set up the
          Worker and connect Google from your computer first (see{' '}
          <code>docs/phase_C3_calendar.md</code>), then enter its address and this device&apos;s key
          here.
        </p>
        <form className={styles.form} onSubmit={connect}>
          <label className={styles.field}>
            <span>Worker address</span>
            <input
              type="url"
              inputMode="url"
              autoComplete="off"
              spellCheck={false}
              placeholder="https://life-helper-edge.<you>.workers.dev"
              value={edgeUrl}
              onChange={(event) => {
                setEdgeUrl(event.target.value)
              }}
              aria-invalid={urlError !== null}
              aria-describedby={urlError ? 'edge-url-error' : undefined}
              required
            />
          </label>
          {urlError ? (
            <p id="edge-url-error" className={styles.error} role="alert">
              {urlError}
            </p>
          ) : null}
          <label className={styles.field}>
            <span>Device key</span>
            <input
              type="password"
              autoComplete="off"
              spellCheck={false}
              value={deviceKey}
              onChange={(event) => {
                setDeviceKey(event.target.value)
              }}
              required
            />
          </label>
          <div className={styles.actions}>
            <Button type="submit">{calendar.connected ? 'Save and check' : 'Connect'}</Button>
            {calendar.connected ? (
              <>
                <Button variant="secondary" onClick={calendar.refreshNow}>
                  Check now
                </Button>
                <Button variant="ghost" onClick={disconnect}>
                  Disconnect this device
                </Button>
              </>
            ) : null}
          </div>
        </form>
        <p className={styles.status} aria-live="polite">
          {calendarStatus(calendar, checkedAt)}
        </p>
      </section>

      <section className={styles.section} aria-labelledby="capacity-settings">
        <h2 id="capacity-settings" className={styles.sectionTitle}>
          Free time
        </h2>
        <p className={styles.help}>
          Today works out free time as your waking hours, minus calendar events, minus a buffer for
          everything a calendar doesn&apos;t show.
        </p>
        <div className={styles.row}>
          <label className={styles.field}>
            <span>Day starts</span>
            <input
              type="time"
              value={capacity.wakeStart}
              onChange={(event) => {
                if (isValidTime(event.target.value)) {
                  setCapacity({ ...capacity, wakeStart: event.target.value })
                }
              }}
            />
          </label>
          <label className={styles.field}>
            <span>Day ends</span>
            <input
              type="time"
              value={capacity.wakeEnd}
              onChange={(event) => {
                if (isValidTime(event.target.value)) {
                  setCapacity({ ...capacity, wakeEnd: event.target.value })
                }
              }}
            />
          </label>
          <label className={styles.field}>
            <span>Buffer (minutes)</span>
            <input
              type="number"
              min={0}
              max={720}
              step={15}
              value={capacity.bufferMinutes}
              onChange={(event) => {
                const minutes = Number(event.target.value)
                if (Number.isFinite(minutes) && minutes >= 0 && minutes <= 720) {
                  setCapacity({ ...capacity, bufferMinutes: Math.round(minutes) })
                }
              }}
            />
          </label>
        </div>
        <p className={styles.help}>
          Buffer: {formatMinutes(capacity.bufferMinutes)} over a full day, less as the day goes on.
        </p>
      </section>

      <section className={styles.section} aria-labelledby="reminder-settings">
        <h2 id="reminder-settings" className={styles.sectionTitle}>
          Evening shutdown
        </h2>
        <label className={styles.field}>
          <span>Remind me from</span>
          <input
            type="time"
            value={shutdownTime}
            onChange={(event) => {
              setShutdownTime(event.target.value)
            }}
          />
        </label>
      </section>

      <section className={styles.section} aria-labelledby="fresh-start-settings">
        <h2 id="fresh-start-settings" className={styles.sectionTitle}>
          Fresh start
        </h2>
        <p className={styles.help}>
          Tasks untouched for this long can be moved to Someday in one go, from Today. Tasks with a
          date or deadline still ahead are never included.
        </p>
        <label className={styles.field}>
          <span>Untouched for (days)</span>
          <input
            type="number"
            min={MIN_THRESHOLD_DAYS}
            max={MAX_THRESHOLD_DAYS}
            step={1}
            value={thresholdDraft ?? thresholdDays}
            onChange={(event) => {
              setThresholdDraft(event.target.value)
              const days = Number(event.target.value)
              if (
                event.target.value !== '' &&
                Number.isInteger(days) &&
                days >= MIN_THRESHOLD_DAYS &&
                days <= MAX_THRESHOLD_DAYS
              ) {
                setThresholdDays(days)
              }
            }}
            onBlur={() => {
              setThresholdDraft(null)
            }}
          />
        </label>
        <p className={styles.status}>
          <Link to="/someday" className={styles.link}>
            Open Someday
          </Link>
        </p>
      </section>

      <section className={styles.section} aria-labelledby="tools-settings">
        <h2 id="tools-settings" className={styles.sectionTitle}>
          Tools
        </h2>
        <p className={styles.help}>
          The component gallery, with its colour-contrast table and the ops replay check for the
          usage log.
        </p>
        <p className={styles.status}>
          <Link to="/gallery" className={styles.link}>
            Open the gallery
          </Link>
        </p>
      </section>
    </div>
  )
}
