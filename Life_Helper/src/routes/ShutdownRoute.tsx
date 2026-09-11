import { useId, useState } from 'react'
import { dbClient } from '../db/client.js'
import { useQuery } from '../db/useQuery.js'
import { localDayKey, startOfLocalDay } from '../scheduling/localDay.js'
import { deferralCutoff } from '../scheduling/schedule.js'
import { useDeferralCutoff } from '../scheduling/useDeferralCutoff.js'
import { committedIds, planSetCompleted, planShutdown, type DayPlanRow } from '../today/dayPlan.js'
import { describeCandidate, describeTask, formatLongDate } from '../today/labels.js'
import { rankCandidates, type Candidate, type DayTask } from '../today/proposal.js'
import { TaskCheck } from '../today/TaskCheck.js'
import { useShutdownTime } from '../today/useShutdownReminder.js'
import { Button } from '../ui/Button.js'
import { EmptyState } from '../ui/EmptyState.js'
import { useRouter } from '../ui/router.js'
import { computeViewState, ThreeStateView } from '../ui/ThreeStateView.js'
import { DAY_PLANS_SQL, DAY_TASKS_SQL, LAST_ACTIVITY_SQL } from './taskQueries.js'
import styles from './ShutdownRoute.module.css'

type Step = 'review' | 'pick' | 'done'

interface LastActivityRow {
  readonly last_active_at: number
}

function isDefined<T>(value: T | undefined): value is T {
  return value !== undefined
}

const MAX_PICKS = 3
const COUNT_WORD = ['', 'one', 'two', 'three']

/**
 * One pickable task: a toggle button whose accessible name is just the
 * title (the detail line is its description, not part of its name), and
 * whose selection shows as a numbered, filled marker *and* aria-pressed.
 * `position` is its place in the picks, or -1 if not picked.
 */
function PickRow({
  title,
  detail,
  position,
  onToggle,
}: {
  title: string
  detail: string
  position: number
  onToggle: () => void
}) {
  const id = useId()
  const isSelected = position !== -1
  return (
    <li>
      <button
        type="button"
        className={styles.pickRow}
        aria-pressed={isSelected}
        aria-labelledby={`${id}-title`}
        aria-describedby={detail ? `${id}-detail` : undefined}
        onClick={onToggle}
      >
        <span className={styles.pickMarker} aria-hidden="true">
          {isSelected ? String(position + 1) : ''}
        </span>
        <span className={styles.pickText}>
          <span id={`${id}-title`} className={styles.pickTitle}>
            {title}
          </span>
          {detail ? (
            <span id={`${id}-detail`} className={styles.pickDetail}>
              {detail}
            </span>
          ) : null}
        </span>
      </button>
    </li>
  )
}

/**
 * Part C2's evening shutdown: a short, two-step ritual that has to finish
 * in under a minute. First, today — what got done, and a checkbox on
 * anything still open that was actually finished. Then tomorrow's three,
 * preselected from the same ranking Today's proposal uses, so on a normal
 * evening the whole thing is "Next," glance, "Set tomorrow's three." One
 * commit writes the three into tomorrow's `day_plans` row and marks
 * tonight's shutdown done (planShutdown()).
 *
 * After a 3+ day absence (Decision 7's cold state) the review is skipped:
 * there's no useful "look back" at days that weren't lived in the app, and
 * a list of them would read as a reckoning.
 */
export function ShutdownRoute() {
  const { navigate } = useRouter()
  const cutoff = useDeferralCutoff()
  const todayStart = startOfLocalDay(cutoff - 1)
  const tomorrowStart = cutoff
  const todayKey = localDayKey(todayStart)
  const tomorrowKey = localDayKey(tomorrowStart)

  // Deferral judged against *tomorrow*: a task deferred until tomorrow is
  // a perfectly good pick for tomorrow's three.
  const tasksQuery = useQuery<DayTask>(DAY_TASKS_SQL, [deferralCutoff(tomorrowStart), todayStart], {
    tables: ['items', 'task_fields'],
  })
  const plansQuery = useQuery<DayPlanRow>(DAY_PLANS_SQL, [todayKey, tomorrowKey], {
    tables: ['day_plans'],
  })
  const { data: activity } = useQuery<LastActivityRow>(LAST_ACTIVITY_SQL, [], {
    tables: ['items', 'task_fields', 'day_plans'],
  })
  const [shutdownTime, setShutdownTime] = useShutdownTime()
  const [step, setStep] = useState<Step | null>(null)
  // null until the user changes something: until then the selection is
  // whatever the default is (tomorrow's existing three, or the proposal),
  // recomputed from live data rather than frozen at first render.
  const [selection, setSelection] = useState<readonly string[] | null>(null)
  const [limitHint, setLimitHint] = useState(false)
  const [othersShown, setOthersShown] = useState(false)

  if (tasksQuery.loading || plansQuery.loading) {
    return <div className={styles.shutdown} aria-busy="true" />
  }

  const tasks = tasksQuery.data
  const byId = new Map(tasks.map((task) => [task.id, task]))
  const todayPlan = plansQuery.data.find((row) => row.day === todayKey)
  const tomorrowPlan = plansQuery.data.find((row) => row.day === tomorrowKey)
  const todaysThree = committedIds(todayPlan)

  const doneToday = tasks
    .filter((task) => task.completed_at !== null)
    .sort((a, b) => (a.completed_at ?? 0) - (b.completed_at ?? 0))
  const openTasks = tasks.filter((task) => task.completed_at === null)
  const openToday = openTasks
    .filter(
      (task) =>
        todaysThree.includes(task.id) ||
        (task.scheduled_for !== null && task.scheduled_for < tomorrowStart) ||
        (task.due_at !== null && task.due_at < tomorrowStart),
    )
    .sort((a, b) => Number(todaysThree.includes(b.id)) - Number(todaysThree.includes(a.id)))

  const ranked = rankCandidates(openTasks, tomorrowStart)
  const rankedIds = new Set(ranked.map((candidate) => candidate.task.id))
  const others = openTasks
    .filter((task) => !rankedIds.has(task.id))
    .sort((a, b) => b.created_at - a.created_at)

  const alreadyPlanned = committedIds(tomorrowPlan).filter(
    (id) => byId.get(id)?.completed_at === null,
  )
  const defaultSelection =
    alreadyPlanned.length > 0
      ? alreadyPlanned
      : ranked.slice(0, MAX_PICKS).map((candidate) => candidate.task.id)
  const selected = (selection ?? defaultSelection).filter(
    (id) => byId.get(id)?.completed_at === null,
  )

  const isEmpty = openTasks.length === 0 && doneToday.length === 0
  const viewState = computeViewState(isEmpty, activity.at(0)?.last_active_at ?? null)
  const currentStep: Step = step ?? (viewState === 'cold' ? 'pick' : 'review')

  function toggle(id: string): void {
    if (selected.includes(id)) {
      setSelection(selected.filter((selectedId) => selectedId !== id))
      setLimitHint(false)
      return
    }
    if (selected.length >= MAX_PICKS) {
      setLimitHint(true)
      return
    }
    setSelection([...selected, id])
    setLimitHint(false)
  }

  function commit(): void {
    const picks = selected.map((id) => byId.get(id)).filter(isDefined)
    const plan = planShutdown({
      todayStart,
      tomorrowStart,
      picks,
      existingToday: todayPlan,
      existingTomorrow: tomorrowPlan,
    })
    void dbClient.mutate({ writes: plan.writes })
    setStep('done')
  }

  function pickRow(task: DayTask, candidate?: Candidate) {
    return (
      <PickRow
        key={task.id}
        title={task.title}
        detail={
          candidate
            ? describeCandidate(candidate, tomorrowStart)
            : describeTask(task, tomorrowStart)
        }
        position={selected.indexOf(task.id)}
        onToggle={() => {
          toggle(task.id)
        }}
      />
    )
  }

  const review = (
    <section className={styles.step} aria-labelledby="review-heading">
      <h2 id="review-heading" className={styles.stepTitle}>
        Today
      </h2>
      {doneToday.length === 0 && openToday.length === 0 ? (
        <p className={styles.note}>A quiet day — nothing was lined up.</p>
      ) : null}
      {doneToday.length > 0 ? (
        <div className={styles.group}>
          <h3 className={styles.groupTitle}>Done</h3>
          <div className={styles.list}>
            {doneToday.map((task) => (
              <TaskCheck
                key={task.id}
                title={task.title}
                done
                onToggle={(done) => {
                  void dbClient.mutate({ writes: planSetCompleted(task, done).writes })
                }}
              />
            ))}
          </div>
        </div>
      ) : null}
      {openToday.length > 0 ? (
        <div className={styles.group}>
          <h3 className={styles.groupTitle}>Still open — tick anything you finished</h3>
          <div className={styles.list}>
            {openToday.map((task) => (
              <TaskCheck
                key={task.id}
                title={task.title}
                detail={describeTask(task, todayStart)}
                done={false}
                onToggle={(done) => {
                  void dbClient.mutate({ writes: planSetCompleted(task, done).writes })
                }}
              />
            ))}
          </div>
        </div>
      ) : null}
      <Button
        onClick={() => {
          setStep('pick')
        }}
      >
        Next: tomorrow&apos;s three
      </Button>
    </section>
  )

  const pick = (
    <section className={styles.step} aria-labelledby="pick-heading">
      <h2 id="pick-heading" className={styles.stepTitle}>
        Tomorrow&apos;s three
      </h2>
      <p className={styles.note}>Pick up to three for {formatLongDate(tomorrowStart)}.</p>
      {ranked.length > 0 ? (
        <ul className={styles.pickList} aria-label="Suggested for tomorrow">
          {ranked.map((candidate) => pickRow(candidate.task, candidate))}
        </ul>
      ) : (
        <p className={styles.note}>Nothing is scheduled or due tomorrow yet.</p>
      )}
      {others.length > 0 ? (
        othersShown ? (
          <ul className={styles.pickList} aria-label="Other open tasks">
            {others.map((task) => pickRow(task))}
          </ul>
        ) : (
          <Button
            variant="ghost"
            onClick={() => {
              setOthersShown(true)
            }}
          >
            Choose from other open tasks
          </Button>
        )
      ) : null}
      <p className={styles.hint} aria-live="polite">
        {limitHint ? 'Three is the limit — unpick one first.' : ''}
      </p>
      <div className={styles.actions}>
        <Button onClick={commit}>
          {selected.length === 0
            ? 'Finish without picking'
            : `Set tomorrow's ${COUNT_WORD[selected.length]}`}
        </Button>
        {viewState !== 'cold' ? (
          <Button
            variant="ghost"
            onClick={() => {
              setStep('review')
            }}
          >
            Back
          </Button>
        ) : null}
      </div>
    </section>
  )

  const done = (
    <section className={styles.step} aria-labelledby="done-heading">
      <h2 id="done-heading" className={styles.stepTitle}>
        Tomorrow is set.
      </h2>
      {selected.length > 0 ? (
        <ol className={styles.doneList}>
          {selected.map((id) => (
            <li key={id}>{byId.get(id)?.title}</li>
          ))}
        </ol>
      ) : (
        <p className={styles.note}>No three this time — Today will suggest some in the morning.</p>
      )}
      <p className={styles.note}>That&apos;s the day closed. Good night.</p>
      <Button
        onClick={() => {
          navigate('/')
        }}
      >
        Back to Today
      </Button>
    </section>
  )

  const flow = currentStep === 'done' ? done : currentStep === 'pick' ? pick : review

  return (
    <div className={styles.shutdown}>
      <header className={styles.header}>
        <h1 className={styles.pageTitle}>Evening shutdown</h1>
        {todayPlan?.shutdown_completed_at != null && currentStep !== 'done' ? (
          <p className={styles.note}>
            Already done tonight — going through it again replaces tomorrow&apos;s three.
          </p>
        ) : null}
      </header>

      <ThreeStateView
        state={viewState}
        empty={
          <EmptyState
            message="Nothing to look back on or plan yet. Capture a few things and they'll show up here."
            actionLabel="Go to Capture"
            onAction={() => {
              navigate('/capture')
            }}
          />
        }
        cold={
          <>
            <p className={styles.note}>
              Welcome back. No need to look back — just pick for tomorrow.
            </p>
            {flow}
          </>
        }
        loaded={flow}
      />

      <label className={styles.reminder}>
        <span>Evening reminder</span>
        <input
          type="time"
          value={shutdownTime}
          onChange={(event) => {
            setShutdownTime(event.target.value)
          }}
        />
        <span className={styles.reminderHelp}>Today prompts you from this time.</span>
      </label>
    </div>
  )
}
