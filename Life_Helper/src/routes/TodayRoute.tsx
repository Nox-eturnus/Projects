import { useState } from 'react'
import { dbClient } from '../db/client.js'
import { useQuery } from '../db/useQuery.js'
import { addLocalDays, localDayKey, startOfLocalDay } from '../scheduling/localDay.js'
import { useDeferralCutoff } from '../scheduling/useDeferralCutoff.js'
import {
  committedIds,
  planCommitTop3,
  planSetCompleted,
  type DayPlanRow,
} from '../today/dayPlan.js'
import { describeCandidate, describeTask, formatLongDate, theseN } from '../today/labels.js'
import { rankCandidates, type DayTask } from '../today/proposal.js'
import { TaskCheck } from '../today/TaskCheck.js'
import { useShutdownTime, useShutdownTimeReached } from '../today/useShutdownReminder.js'
import { Button } from '../ui/Button.js'
import { EmptyState } from '../ui/EmptyState.js'
import { Link, useRouter } from '../ui/router.js'
import { computeViewState, ThreeStateView } from '../ui/ThreeStateView.js'
import { UndoToast } from '../ui/UndoToast.js'
import { useUndoToast } from '../ui/useUndoToast.js'
import { DAY_PLANS_SQL, DAY_TASKS_SQL, LAST_ACTIVITY_SQL } from './taskQueries.js'
import styles from './TodayRoute.module.css'

interface LastActivityRow {
  readonly last_active_at: number
}

function isDefined<T>(value: T | undefined): value is T {
  return value !== undefined
}

/** Open work first, in the order the day runs; anything already done today last. */
function byDayOrder(a: DayTask, b: DayTask): number {
  const aDone = a.completed_at !== null
  const bDone = b.completed_at !== null
  if (aDone !== bDone) return aDone ? 1 : -1
  const when = (task: DayTask) => task.scheduled_for ?? task.due_at ?? Number.MAX_SAFE_INTEGER
  return when(a) - when(b) || a.created_at - b.created_at
}

/**
 * Part C2's Today: exactly three committed tasks, prominently, above
 * everything else — picked the evening before by the shutdown ritual, or,
 * if that was skipped, proposed here (due, then carried over, then oldest
 * scheduled — see proposal.ts) for one tap to accept or swap. Below them,
 * the rest of the day's work, visually secondary. Once all three are done,
 * the page says so and stops there: the rest of today stays folded away
 * behind an explicit "show," rather than a finished day immediately
 * refilling itself with more.
 *
 * Everything is scoped to today's local date (`day_plans.day`), which
 * rolls over at midnight on its own via useDeferralCutoff().
 */
export function TodayRoute() {
  const { navigate } = useRouter()
  const cutoff = useDeferralCutoff()
  const todayStart = startOfLocalDay(cutoff - 1)
  const todayKey = localDayKey(todayStart)

  // Completed since *yesterday*: a task committed at last night's shutdown
  // and ticked off before midnight should still show as done in today's
  // three, not vanish from its slot.
  const tasksQuery = useQuery<DayTask>(DAY_TASKS_SQL, [cutoff, addLocalDays(todayStart, -1)], {
    tables: ['items', 'task_fields'],
  })
  const plansQuery = useQuery<DayPlanRow>(DAY_PLANS_SQL, [todayKey, todayKey], {
    tables: ['day_plans'],
  })
  const { data: activity } = useQuery<LastActivityRow>(LAST_ACTIVITY_SQL, [], {
    tables: ['items', 'task_fields', 'day_plans'],
  })
  const [shutdownTime] = useShutdownTime()
  const shutdownTimeReached = useShutdownTimeReached(todayStart, shutdownTime)
  // Swaps only live for the day they were made on and aren't persisted: a
  // proposal is a suggestion until accepted, never a stored decision.
  const [swapped, setSwapped] = useState<{ day: string; ids: ReadonlySet<string> }>(() => ({
    day: todayKey,
    ids: new Set(),
  }))
  const [restShown, setRestShown] = useState(false)
  const undo = useUndoToast()

  const header = (
    <header className={styles.header}>
      <h1 className={styles.pageTitle}>Today</h1>
      <p className={styles.date}>{formatLongDate(todayStart)}</p>
    </header>
  )

  if (tasksQuery.loading || plansQuery.loading) {
    return (
      <div className={styles.today} aria-busy="true">
        {header}
      </div>
    )
  }

  const tasks = tasksQuery.data
  const plan = plansQuery.data.find((row) => row.day === todayKey)
  const byId = new Map(tasks.map((task) => [task.id, task]))
  // A committed task that has since been deleted, moved to someday, or
  // deferred simply drops out of its slot; if none are left, Today falls
  // back to proposing, as if nothing had been committed.
  const committed = committedIds(plan)
    .map((id) => byId.get(id))
    .filter(isDefined)
  const isCommitted = committed.length > 0

  const excluded = swapped.day === todayKey ? swapped.ids : new Set<string>()
  const available = isCommitted
    ? []
    : rankCandidates(tasks, todayStart).filter((candidate) => !excluded.has(candidate.task.id))
  const proposal = available.slice(0, 3)
  const canSwap = available.length > proposal.length

  const topIds = new Set(
    isCommitted ? committed.map((task) => task.id) : proposal.map((c) => c.task.id),
  )
  const rest = tasks
    .filter((task) => {
      if (topIds.has(task.id)) return false
      if (task.completed_at !== null) return task.completed_at >= todayStart
      return (
        (task.scheduled_for !== null && task.scheduled_for < cutoff) ||
        (task.due_at !== null && task.due_at < cutoff)
      )
    })
    .sort(byDayOrder)

  const allDone = isCommitted && committed.every((task) => task.completed_at !== null)
  const isEmpty = !isCommitted && proposal.length === 0 && rest.length === 0
  const viewState = computeViewState(isEmpty, activity.at(0)?.last_active_at ?? null)
  const shutdownDone = plan?.shutdown_completed_at != null

  function accept(): void {
    const commit = planCommitTop3({
      dayStart: todayStart,
      tasks: proposal.map((candidate) => candidate.task),
      via: 'proposal',
      existing: plan,
    })
    void dbClient.mutate({ writes: commit.writes })
    undo.show("Today's three are set", () => {
      void dbClient.mutate({ writes: commit.undoWrites })
    })
  }

  function swap(id: string): void {
    setSwapped({ day: todayKey, ids: new Set([...excluded, id]) })
  }

  function setDone(task: DayTask, done: boolean): void {
    void dbClient.mutate({ writes: planSetCompleted(task, done).writes })
  }

  function topThree(intro: string) {
    if (isCommitted) {
      return (
        <section className={styles.topThree} aria-labelledby="top-three-heading">
          <h2 id="top-three-heading" className={styles.sectionTitle}>
            Your three
          </h2>
          <div className={styles.topList}>
            {committed.map((task) => (
              <TaskCheck
                key={task.id}
                emphasis="prominent"
                title={task.title}
                detail={describeTask(task, todayStart)}
                done={task.completed_at !== null}
                onToggle={(done) => {
                  setDone(task, done)
                }}
              />
            ))}
          </div>
          {allDone ? (
            <p className={styles.finish} role="status">
              That&apos;s all three. The rest of the day is yours.
            </p>
          ) : null}
        </section>
      )
    }

    if (proposal.length === 0) {
      return (
        <section className={styles.topThree} aria-labelledby="top-three-heading">
          <h2 id="top-three-heading" className={styles.sectionTitle}>
            Your three
          </h2>
          <p className={styles.intro}>Nothing else needs picking today.</p>
        </section>
      )
    }

    return (
      <section className={styles.topThree} aria-labelledby="top-three-heading">
        <h2 id="top-three-heading" className={styles.sectionTitle}>
          Three to start with
        </h2>
        <p className={styles.intro}>{intro}</p>
        <ol className={styles.proposalList}>
          {proposal.map((candidate) => (
            <li key={candidate.task.id} className={styles.proposalItem}>
              <span className={styles.proposalText}>
                <span className={styles.proposalTitle}>{candidate.task.title}</span>
                <span className={styles.proposalReason}>
                  {describeCandidate(candidate, todayStart)}
                </span>
              </span>
              <Button
                variant="ghost"
                size="sm"
                aria-label={`Swap ${candidate.task.title}`}
                title={canSwap ? undefined : 'Nothing else to swap in'}
                disabled={!canSwap}
                onClick={() => {
                  swap(candidate.task.id)
                }}
              >
                Swap
              </Button>
            </li>
          ))}
        </ol>
        <Button onClick={accept}>Accept {theseN(proposal.length)}</Button>
      </section>
    )
  }

  const openRest = rest.filter((task) => task.completed_at === null)
  const restList = (
    <section className={styles.rest} aria-labelledby="rest-heading">
      <h2 id="rest-heading" className={styles.restTitle}>
        Also today
      </h2>
      <div className={styles.restList}>
        {rest.map((task) => (
          <TaskCheck
            key={task.id}
            title={task.title}
            detail={describeTask(task, todayStart)}
            done={task.completed_at !== null}
            onToggle={(done) => {
              setDone(task, done)
            }}
          />
        ))}
      </div>
    </section>
  )
  let restSection = null
  if (allDone && !restShown) {
    // No count on the button: a finished day isn't the moment to announce
    // how much is left (Decision 7).
    restSection =
      openRest.length > 0 ? (
        <Button
          variant="ghost"
          onClick={() => {
            setRestShown(true)
          }}
        >
          Show the rest of today
        </Button>
      ) : null
  } else if (rest.length > 0) {
    restSection = restList
  }

  return (
    <div className={styles.today}>
      {header}

      {shutdownTimeReached && !shutdownDone && !isEmpty ? (
        <section className={styles.prompt} aria-label="Evening shutdown">
          <p className={styles.promptText}>
            Evening shutdown: look back at today and pick tomorrow&apos;s three.
          </p>
          <Button
            onClick={() => {
              navigate('/shutdown')
            }}
          >
            Start shutdown
          </Button>
        </section>
      ) : null}

      <ThreeStateView
        state={viewState}
        empty={
          <EmptyState
            message="Nothing lined up for today. Anything you schedule, or give a deadline, shows up here."
            actionLabel="Capture something"
            onAction={() => {
              navigate('/capture')
            }}
          />
        }
        cold={
          <>
            <p className={styles.coldMessage}>Welcome back. No catching up needed.</p>
            {topThree("Here's a fresh three for today. Accept, or swap any you'd rather leave.")}
          </>
        }
        loaded={
          <>
            {topThree(
              "Nothing was picked last night, so here's a start. Accept, or swap any you'd rather leave.",
            )}
            {restSection}
          </>
        }
      />

      {isEmpty ? null : (
        <footer className={styles.footer}>
          {shutdownDone ? <span className={styles.footerNote}>Tomorrow is planned.</span> : null}
          <Link to="/shutdown" className={styles.footerLink}>
            Evening shutdown
          </Link>
        </footer>
      )}

      <UndoToast pending={undo.pending} onUndo={undo.runUndo} />
    </div>
  )
}
