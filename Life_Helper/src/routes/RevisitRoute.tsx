import { useId, useState, type SyntheticEvent } from 'react'
import { dbClient } from '../db/client.js'
import { useQuery } from '../db/useQuery.js'
import { localDayKey, startOfLocalDay } from '../scheduling/localDay.js'
import { useDeferralCutoff } from '../scheduling/useDeferralCutoff.js'
import { findSlipping } from '../slipping/slipping.js'
import {
  MAX_STEPS,
  planBreakDown,
  planDoItNow,
  planLetGo,
  planScheduleForToday,
  type LetGoChoice,
  type SlippingTask,
  type StepsWhen,
} from '../slipping/slippingActions.js'
import { committedIds, type DayPlanRow, type WritePlan } from '../today/dayPlan.js'
import { describeSlipping } from '../today/labels.js'
import { Button } from '../ui/Button.js'
import { EmptyState } from '../ui/EmptyState.js'
import { useRouter } from '../ui/router.js'
import { Sheet } from '../ui/Sheet.js'
import { computeViewState, ThreeStateView } from '../ui/ThreeStateView.js'
import { UndoToast } from '../ui/UndoToast.js'
import { useUndoToast } from '../ui/useUndoToast.js'
import { DAY_PLANS_SQL, LAST_ACTIVITY_SQL, SLIPPING_SQL } from './taskQueries.js'
import styles from './RevisitRoute.module.css'

interface LastActivityRow {
  readonly last_active_at: number
}

/** How many a cold return shows before "Show the rest" — a few to decide on, not a backlog. */
const COLD_PREVIEW = 3

type OpenSheet =
  | { readonly kind: 'replace'; readonly task: SlippingTask }
  | { readonly kind: 'breakDown'; readonly task: SlippingTask }
  | { readonly kind: 'letGo'; readonly task: SlippingTask }

const WHEN_OPTIONS: { value: StepsWhen; label: string }[] = [
  { value: 'today', label: 'Today' },
  { value: 'tomorrow', label: 'Tomorrow' },
  { value: 'inbox', label: 'Inbox, to decide later' },
]

/**
 * Part C4's slipping view, called Revisit where it's seen: the tasks that
 * keep getting moved (findSlipping()), most-moved first. Each offers
 * exactly three ways out — do it now, break it down, let it go — and every
 * one is undoable from the toast.
 *
 * Decision 7: there's no count of how many are here, no "overdue," and
 * nothing framed as a failure; a task is here because it needs a decision,
 * not more effort. After 3+ days away it shows a few, not the whole list.
 */
export function RevisitRoute() {
  const { navigate } = useRouter()
  const cutoff = useDeferralCutoff()
  const todayStart = startOfLocalDay(cutoff - 1)
  const todayKey = localDayKey(todayStart)

  const tasksQuery = useQuery<SlippingTask>(SLIPPING_SQL, [cutoff, todayStart], {
    tables: ['items', 'task_fields', 'links'],
  })
  const plansQuery = useQuery<DayPlanRow>(DAY_PLANS_SQL, [todayKey, todayKey], {
    tables: ['day_plans'],
  })
  const { data: activity } = useQuery<LastActivityRow>(LAST_ACTIVITY_SQL, [], {
    tables: ['items', 'task_fields', 'day_plans', 'links'],
  })
  const undo = useUndoToast()
  const [sheet, setSheet] = useState<OpenSheet | null>(null)
  const [restShown, setRestShown] = useState(false)

  const header = (
    <header className={styles.header}>
      <h1 className={styles.pageTitle}>Revisit</h1>
    </header>
  )

  if (tasksQuery.loading || plansQuery.loading) {
    return (
      <div className={styles.revisit} aria-busy="true">
        {header}
      </div>
    )
  }

  const tasks = tasksQuery.data
  const byId = new Map(tasks.map((task) => [task.id, task]))
  const plan = plansQuery.data.find((row) => row.day === todayKey)
  // Today's three as Today shows them: committed ids that still resolve.
  const slots = committedIds(plan)
    .map((id) => byId.get(id))
    .filter((task): task is SlippingTask => task !== undefined)
  const slipping = findSlipping(tasks, todayStart, new Set(slots.map((task) => task.id)))
  const viewState = computeViewState(slipping.length === 0, activity.at(0)?.last_active_at ?? null)

  function apply(writePlan: WritePlan, label: string): void {
    setSheet(null)
    void dbClient.mutate({ writes: writePlan.writes })
    undo.show(label, () => {
      void dbClient.mutate({ writes: writePlan.undoWrites })
    })
  }

  function doItNow(task: SlippingTask): void {
    if (slots.length < 3) {
      apply(
        planDoItNow({ task, dayStart: todayStart, slots, existing: plan }),
        "Added to today's three",
      )
    } else if (slots.some((slot) => slot.completed_at === null)) {
      setSheet({ kind: 'replace', task })
    } else {
      // All three are done: nothing worth replacing, so it joins the rest of today.
      apply(planScheduleForToday(task, todayStart), 'Added to today')
    }
  }

  function replace(task: SlippingTask, slotId: string): void {
    apply(
      planDoItNow({ task, dayStart: todayStart, slots, existing: plan, replace: slotId }),
      "Added to today's three",
    )
  }

  function breakDown(task: SlippingTask, steps: string[], when: StepsWhen): void {
    const writePlan = planBreakDown({ parent: task, steps, when, dayStart: todayStart })
    const count = writePlan.stepIds.length
    apply(writePlan, count === 1 ? 'Replaced with 1 step' : `Split into ${String(count)} steps`)
  }

  function letGo(task: SlippingTask, choice: LetGoChoice): void {
    apply(planLetGo(task, choice), choice === 'someday' ? 'Moved to someday' : 'Deleted')
  }

  function list(items: readonly SlippingTask[]) {
    return (
      <ul className={styles.list}>
        {items.map((task) => (
          <SlippingCard
            key={task.id}
            task={task}
            detail={describeSlipping(task, todayStart)}
            onDoItNow={() => {
              doItNow(task)
            }}
            onBreakDown={() => {
              setSheet({ kind: 'breakDown', task })
            }}
            onLetGo={() => {
              setSheet({ kind: 'letGo', task })
            }}
          />
        ))}
      </ul>
    )
  }

  const closeSheet = () => {
    setSheet(null)
  }

  return (
    <div className={styles.revisit}>
      {header}

      <ThreeStateView
        state={viewState}
        empty={
          <EmptyState
            message="Nothing needs a second look. When a task keeps getting moved, it shows up here so you can decide what to do with it."
            actionLabel="Go to Today"
            onAction={() => {
              navigate('/')
            }}
          />
        }
        cold={
          <>
            <p className={styles.lede}>
              Welcome back. There&apos;s nothing to catch up on here — these will keep until
              you&apos;re ready. A few, if you&apos;d like to decide on them now:
            </p>
            {list(restShown ? slipping : slipping.slice(0, COLD_PREVIEW))}
            {!restShown && slipping.length > COLD_PREVIEW ? (
              <Button
                variant="ghost"
                className={styles.showRest}
                onClick={() => {
                  setRestShown(true)
                }}
              >
                Show the rest
              </Button>
            ) : null}
          </>
        }
        loaded={
          <>
            <p className={styles.lede}>
              Tasks that keep getting moved. Each one needs a decision, not more effort: do it now,
              break it into smaller steps, or let it go.
            </p>
            {list(slipping)}
          </>
        }
      />

      <Sheet open={sheet?.kind === 'replace'} onClose={closeSheet} title="Today's three are full">
        {sheet?.kind === 'replace' ? (
          <div className={styles.sheetBody}>
            <p className={styles.sheetNote}>
              Which one should &ldquo;{sheet.task.title}&rdquo; take the place of? The one it
              replaces stays on today&apos;s list.
            </p>
            <div className={styles.choiceList}>
              {slots
                .filter((slot) => slot.completed_at === null)
                .map((slot) => (
                  <Button
                    key={slot.id}
                    variant="secondary"
                    onClick={() => {
                      replace(sheet.task, slot.id)
                    }}
                  >
                    Replace {slot.title}
                  </Button>
                ))}
            </div>
          </div>
        ) : null}
      </Sheet>

      <Sheet open={sheet?.kind === 'breakDown'} onClose={closeSheet} title="Break it down">
        {sheet?.kind === 'breakDown' ? (
          <BreakDownForm
            key={sheet.task.id}
            task={sheet.task}
            onSubmit={(steps, when) => {
              breakDown(sheet.task, steps, when)
            }}
          />
        ) : null}
      </Sheet>

      <Sheet open={sheet?.kind === 'letGo'} onClose={closeSheet} title="Let it go">
        {sheet?.kind === 'letGo' ? (
          <div className={styles.sheetBody}>
            <p className={styles.sheetNote}>
              Someday keeps &ldquo;{sheet.task.title}&rdquo; out of your lists and counts until you
              want it back. Delete removes it.
            </p>
            <div className={styles.choiceList}>
              <Button
                onClick={() => {
                  letGo(sheet.task, 'someday')
                }}
              >
                Move to someday
              </Button>
              <Button
                variant="secondary"
                onClick={() => {
                  letGo(sheet.task, 'delete')
                }}
              >
                Delete
              </Button>
            </div>
          </div>
        ) : null}
      </Sheet>

      <UndoToast pending={undo.pending} onUndo={undo.runUndo} />
    </div>
  )
}

function SlippingCard({
  task,
  detail,
  onDoItNow,
  onBreakDown,
  onLetGo,
}: {
  task: SlippingTask
  detail: string
  onDoItNow: () => void
  onBreakDown: () => void
  onLetGo: () => void
}) {
  const titleId = useId()
  return (
    <li className={styles.card} aria-labelledby={titleId}>
      <div className={styles.text}>
        <span id={titleId} className={styles.title}>
          {task.title}
        </span>
        {detail ? <span className={styles.detail}>{detail}</span> : null}
      </div>
      <div className={styles.actions} role="group" aria-labelledby={titleId}>
        <Button size="sm" onClick={onDoItNow}>
          Do it now
        </Button>
        <Button size="sm" variant="secondary" onClick={onBreakDown}>
          Break it down
        </Button>
        <Button size="sm" variant="ghost" onClick={onLetGo}>
          Let it go
        </Button>
      </div>
    </li>
  )
}

function BreakDownForm({
  task,
  onSubmit,
}: {
  task: SlippingTask
  onSubmit: (steps: string[], when: StepsWhen) => void
}) {
  const [steps, setSteps] = useState(['', ''])
  const [when, setWhen] = useState<StepsWhen>('today')
  const whenName = useId()
  const hasStep = steps.some((step) => step.trim().length > 0)

  function submit(event: SyntheticEvent<HTMLFormElement>): void {
    event.preventDefault()
    if (hasStep) onSubmit(steps, when)
  }

  return (
    <form className={styles.sheetBody} onSubmit={submit}>
      <p className={styles.sheetNote}>
        Smaller steps for &ldquo;{task.title}&rdquo;. The original is archived — kept, but out of
        your lists.
      </p>
      {steps.map((step, index) => (
        <label key={index} className={styles.field}>
          <span>Step {index + 1}</span>
          <input
            value={step}
            onChange={(event) => {
              const next = [...steps]
              next[index] = event.target.value
              setSteps(next)
            }}
          />
        </label>
      ))}
      {steps.length < MAX_STEPS ? (
        <Button
          variant="ghost"
          size="sm"
          className={styles.addStep}
          onClick={() => {
            setSteps([...steps, ''])
          }}
        >
          Add another step
        </Button>
      ) : null}
      <fieldset className={styles.when}>
        <legend>When</legend>
        {WHEN_OPTIONS.map((option) => (
          <label key={option.value} className={styles.whenOption}>
            <input
              type="radio"
              name={whenName}
              value={option.value}
              checked={when === option.value}
              onChange={() => {
                setWhen(option.value)
              }}
            />
            {option.label}
          </label>
        ))}
      </fieldset>
      <Button type="submit" disabled={!hasStep}>
        Break it down
      </Button>
    </form>
  )
}
