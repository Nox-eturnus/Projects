import { useState } from 'react'
import { dbClient } from '../db/client.js'
import { useQuery } from '../db/useQuery.js'
import { deferralCutoff } from '../scheduling/schedule.js'
import { AMNESTY_ELIGIBLE_SQL, LATEST_SWEEP_SQL, SWEPT_ITEMS_SQL } from '../routes/taskQueries.js'
import { formatAsOf } from '../today/labels.js'
import { Button } from '../ui/Button.js'
import { Link } from '../ui/router.js'
import { Sheet } from '../ui/Sheet.js'
import {
  canUndoSweep,
  planSweep,
  planUndoSweep,
  undoDeadline,
  untouchedBefore,
  useThresholdDays,
  type EligibleTask,
  type SweepRow,
} from './amnesty.js'
import styles from './FreshStart.module.css'

/**
 * Part C5's amnesty control, on Today ("one action from Today"). The plan
 * calls it amnesty; the user sees "Fresh start", because nothing here was
 * a wrongdoing to be pardoned (Decision 7).
 *
 * Shows nothing at all unless there's something to offer: either tasks
 * have aged past the threshold — then a quiet offer, with no count — or a
 * sweep in the last 24 hours can still be undone. The confirmation is the
 * one place the count appears (the plan: "shows the count"), and the sweep
 * writes exactly the tasks that count was taken from.
 */
export function FreshStart({
  todayStart,
  now,
  onUndoable,
}: {
  todayStart: number
  now: number
  /** Today's undo toast: the sweep is undoable there at once, as well as for 24 hours here. */
  onUndoable: (label: string, undo: () => void) => void
}) {
  const [thresholdDays] = useThresholdDays()
  const eligibleQuery = useQuery<EligibleTask>(
    AMNESTY_ELIGIBLE_SQL,
    [deferralCutoff(todayStart), todayStart, untouchedBefore(todayStart, thresholdDays)],
    { tables: ['items', 'task_fields', 'links', 'day_plans', 'amnesty_sweeps'] },
  )
  const sweepQuery = useQuery<SweepRow>(LATEST_SWEEP_SQL, [], { tables: ['amnesty_sweeps'] })
  // The exact tasks the confirmation counted — what the sweep will write,
  // even if something changes underneath while the sheet is open.
  const [confirming, setConfirming] = useState<readonly EligibleTask[] | null>(null)

  if (eligibleQuery.loading || sweepQuery.loading) return null

  const eligible = eligibleQuery.data
  const sweep = sweepQuery.data.at(0)
  const undoable = canUndoSweep(sweep, now)

  function sweepNow(tasks: readonly EligibleTask[]): void {
    setConfirming(null)
    const plan = planSweep({ tasks, thresholdDays })
    void dbClient.mutate({ writes: plan.writes })
    onUndoable('Moved to Someday', () => {
      void dbClient.mutate({ writes: plan.undoWrites })
    })
  }

  async function undoSweep(target: SweepRow): Promise<void> {
    const rows = await dbClient.query<{ item_id: string }>(SWEPT_ITEMS_SQL, [target.id])
    const plan = planUndoSweep({ sweepId: target.id, itemIds: rows.map((row) => row.item_id) })
    await dbClient.mutate({ writes: plan.writes })
  }

  const count = confirming?.length ?? 0

  return (
    <>
      {undoable ? (
        <section className={styles.note} aria-label="Fresh start">
          <p className={styles.text}>
            Fresh start moved some older tasks to Someday. You can undo it until{' '}
            {formatAsOf(undoDeadline(sweep), now)}.
          </p>
          <span className={styles.actions}>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => {
                void undoSweep(sweep)
              }}
            >
              Undo fresh start
            </Button>
            <Link to="/someday" className={styles.link}>
              See Someday
            </Link>
          </span>
        </section>
      ) : eligible.length > 0 ? (
        <section className={styles.note} aria-label="Fresh start">
          <p className={styles.text}>
            Tasks untouched for {thresholdDays} days or more can move to Someday — kept and
            searchable, just out of the way.
          </p>
          <span className={styles.actions}>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => {
                setConfirming(eligible)
              }}
            >
              Fresh start
            </Button>
          </span>
        </section>
      ) : null}

      <Sheet
        open={confirming !== null}
        onClose={() => {
          setConfirming(null)
        }}
        title="Fresh start"
      >
        {confirming ? (
          <div className={styles.sheetBody}>
            <p className={styles.question}>
              Move {count} {count === 1 ? 'task' : 'tasks'} untouched for {thresholdDays} days or
              more to Someday?
            </p>
            <p className={styles.sheetNote}>
              They&apos;re kept and searchable, and you can bring any of them back. You can undo
              this for 24 hours.
            </p>
            <div className={styles.sheetActions}>
              <Button
                onClick={() => {
                  sweepNow(confirming)
                }}
              >
                Move {count} to Someday
              </Button>
              <Button
                variant="ghost"
                onClick={() => {
                  setConfirming(null)
                }}
              >
                Not now
              </Button>
            </div>
          </div>
        ) : null}
      </Sheet>
    </>
  )
}
