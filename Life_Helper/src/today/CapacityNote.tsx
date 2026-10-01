import { formatMinutes, type Capacity, type Commitment } from '../calendar/capacity.js'
import styles from './CapacityNote.module.css'

/**
 * Part C3's comparison, under the top 3: how much time is free for the
 * rest of today, what the three are estimated to need, and — only when
 * they add up to more than that — a plain note that it may not all fit.
 * It's information for choosing, never a verdict: no red, no "over
 * capacity," and it doesn't pretend to know a task with no estimate.
 */
export function CapacityNote({
  capacity,
  commitment,
}: {
  capacity: Capacity
  commitment: Commitment
}) {
  if (capacity.dayOver) return null

  const free = formatMinutes(capacity.freeMinutes)
  const needs = commitment.estimatedCount > 0 ? formatMinutes(commitment.estimatedMinutes) : null
  const exceeds = needs !== null && commitment.estimatedMinutes > capacity.freeMinutes
  const unestimated =
    commitment.unestimatedCount > 0 && commitment.estimatedCount > 0
      ? ` (${String(commitment.unestimatedCount)} without an estimate)`
      : ''

  return (
    <div className={styles.note}>
      <p className={styles.line}>
        About <strong>{free}</strong> free for the rest of today
        {needs !== null ? (
          <>
            {' '}
            · your three need about <strong>{needs}</strong>
            {unestimated}
          </>
        ) : null}
        .
      </p>
      {exceeds ? (
        <p className={styles.warning} role="status">
          That&apos;s more than the time that&apos;s free — it may not all fit today.
        </p>
      ) : null}
    </div>
  )
}
