import { useState } from 'react'
import { isConnected, parseConnection, CONNECTION_KEY } from '../calendar/calendarStore.js'
import { useQuery } from '../db/useQuery.js'
import {
  CALENDAR_WEEK_DAYS,
  evaluateAmnesty,
  evaluateCalendar,
  evaluateColdStart,
  evaluateShutdowns,
  evaluateUsage,
  GATE_ACTIVITY_SQL,
  GATE_SHUTDOWNS_SQL,
  GATE_SWEEPS_SQL,
  lastDays,
  NEEDS_YOU,
  USAGE_STREAK_DAYS,
  type KeptSweep,
  type Verdict,
} from '../gate/gate.js'
import {
  CALENDAR_HEALTH_KEY,
  COLD_STARTS_KEY,
  deviceInfo,
  OPEN_DAYS_KEY,
  parseCalendarHealth,
  parseColdStarts,
  parseOpenDays,
} from '../gate/gateLog.js'
import { useLocalValue } from '../lib/localStore.js'
import { useNow } from '../lib/useNow.js'
import { addLocalDays, localDayKey, startOfLocalDay } from '../scheduling/localDay.js'
import { Button } from '../ui/Button.js'
import styles from './GateRoute.module.css'

/** How far back the report looks: the usage streak's length, plus a week of context. */
const REPORT_DAYS = USAGE_STREAK_DAYS + CALENDAR_WEEK_DAYS

interface Condition extends Verdict {
  readonly name: string
}

/**
 * Part C6's gate report: every condition evaluated from what this device
 * recorded, with the evidence, a day-by-day table, and a summary to paste
 * into docs/usage_log.md. Nothing is self-reported here, and nothing here
 * marks the gate passed by itself — recording it is still the user's step.
 *
 * Until Phase D syncs devices, each device has its own data: run this on
 * the phone the app is used on.
 */
export function GateRoute() {
  const now = useNow()
  const todayStart = startOfLocalDay(now)
  const since = addLocalDays(todayStart, -(REPORT_DAYS - 1))
  const days = lastDays(todayStart, REPORT_DAYS)

  const activity = useQuery<{ at: number }>(GATE_ACTIVITY_SQL, [since], {
    tables: ['items', 'task_fields'],
  })
  const shutdowns = useQuery<{ day: string }>(GATE_SHUTDOWNS_SQL, [localDayKey(since)], {
    tables: ['day_plans'],
  })
  const sweeps = useQuery<KeptSweep>(GATE_SWEEPS_SQL, [], { tables: ['amnesty_sweeps'] })
  const [coldStarts] = useLocalValue(COLD_STARTS_KEY, parseColdStarts)
  const [openDays] = useLocalValue(OPEN_DAYS_KEY, parseOpenDays)
  const [health] = useLocalValue(CALENDAR_HEALTH_KEY, parseCalendarHealth)
  const [connection] = useLocalValue(CONNECTION_KEY, parseConnection)
  const [copied, setCopied] = useState(false)

  const header = (
    <header className={styles.header}>
      <h1 className={styles.pageTitle}>Today gate</h1>
      <p className={styles.lede}>
        Part C6, measured on this device. Run it on the phone the app is used on: until devices
        sync, each one has only its own data.
      </p>
    </header>
  )

  if (activity.loading || shutdowns.loading || sweeps.loading) {
    return (
      <div className={styles.gate} aria-busy="true">
        {header}
      </div>
    )
  }

  const device = deviceInfo()
  const perDay = new Map<string, number>()
  for (const row of activity.data) {
    const key = localDayKey(row.at)
    perDay.set(key, (perDay.get(key) ?? 0) + 1)
  }
  const activeDays = new Set(perDay.keys())
  const shutdownDays = new Set(shutdowns.data.map((row) => row.day))
  const opened = new Set(openDays)

  const coldStart = evaluateColdStart(coldStarts)
  const conditions: Condition[] = [
    { name: 'Today renders in under 1.5s cold start on a real Android device', ...coldStart },
    {
      name: 'Calendar sync survives a full week without manual intervention',
      ...evaluateCalendar(health, isConnected(connection)),
    },
    {
      name: 'Shutdown ritual completed on at least 5 of 7 days',
      ...evaluateShutdowns(shutdownDays, todayStart),
    },
    {
      name: `${String(USAGE_STREAK_DAYS)} consecutive days meeting the Definition of "used"`,
      ...evaluateUsage(activeDays, todayStart, device.mobile),
    },
    {
      name: 'At least one amnesty sweep (fresh start) on real data',
      ...evaluateAmnesty(sweeps.data),
    },
  ]
  const allPassed = conditions.every((condition) => condition.passed)

  const report = [
    `Today gate report — ${localDayKey(now)} (${device.android ? 'Android' : device.mobile ? 'phone' : 'not a phone'})`,
    '',
    ...conditions.map(
      (condition, i) =>
        `${String(i + 1)}. ${condition.passed ? 'PASS' : 'not yet'} — ${condition.name}: ${condition.evidence}`,
    ),
    '',
    allPassed ? 'All five conditions pass.' : 'Not all conditions pass yet.',
  ].join('\n')

  function copyReport(): void {
    void navigator.clipboard.writeText(report).then(() => {
      setCopied(true)
    })
  }

  return (
    <div className={styles.gate}>
      {header}

      <p className={styles.verdict} role="status">
        {allPassed
          ? 'All five conditions pass. Record the report in docs/usage_log.md to close the gate.'
          : 'Not all conditions pass yet.'}
      </p>

      <ol className={styles.conditions}>
        {conditions.map((condition) => (
          <li key={condition.name} className={styles.condition}>
            <span className={styles.mark} aria-hidden="true">
              {condition.passed ? '✓' : '·'}
            </span>
            <span className={styles.conditionText}>
              <span className={styles.conditionName}>
                {condition.name}
                <span className={styles.visuallyHidden}>
                  {condition.passed ? ' — passes' : ' — not yet'}
                </span>
              </span>
              <span className={styles.evidence}>{condition.evidence}</span>
            </span>
          </li>
        ))}
      </ol>

      <section className={styles.section} aria-labelledby="gate-days">
        <h2 id="gate-days" className={styles.sectionTitle}>
          Day by day
        </h2>
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th scope="col">Day</th>
                <th scope="col">Opened</th>
                <th scope="col">Captured or completed</th>
                <th scope="col">Shutdown</th>
                <th scope="col">Calendar</th>
              </tr>
            </thead>
            <tbody>
              {[...days].reverse().map((day) => {
                const calendar = health.days[day]
                const neededYou = calendar
                  ? NEEDS_YOU.some((problem) => (calendar.problems[problem] ?? 0) > 0)
                  : false
                return (
                  <tr key={day}>
                    <th scope="row">{day}</th>
                    <td>{opened.has(day) ? 'yes' : '—'}</td>
                    <td>{perDay.get(day) ?? 0}</td>
                    <td>{shutdownDays.has(day) ? 'done' : '—'}</td>
                    <td>
                      {calendar
                        ? `${String(calendar.ok)} ok${neededYou ? ', needed you' : ''}`
                        : '—'}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </section>

      <section className={styles.section} aria-labelledby="gate-cold-starts">
        <h2 id="gate-cold-starts" className={styles.sectionTitle}>
          Cold starts
        </h2>
        <p className={styles.help}>
          Each launch that opens on Today records the time from tapping the icon (navigation start)
          to Today showing its tasks. Close the app fully before launching it to get a true cold
          start.
        </p>
        {coldStarts.length === 0 ? (
          <p className={styles.help}>None recorded on this device yet.</p>
        ) : (
          <ul className={styles.samples}>
            {[...coldStarts].reverse().map((sample) => (
              <li key={sample.at}>
                {new Date(sample.at).toLocaleString()} — {sample.ms}ms
                {sample.android ? '' : ' (not Android)'}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className={styles.section} aria-labelledby="gate-report">
        <h2 id="gate-report" className={styles.sectionTitle}>
          Report
        </h2>
        <pre className={styles.report}>{report}</pre>
        <Button variant="secondary" onClick={copyReport}>
          {copied ? 'Copied' : 'Copy report'}
        </Button>
      </section>
    </div>
  )
}
