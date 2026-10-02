import { useId, useState } from 'react'
import {
  planBringBack,
  toFtsQuery,
  type BringBackTo,
  type SomedayTask,
} from '../amnesty/amnesty.js'
import { dbClient } from '../db/client.js'
import { useQuery } from '../db/useQuery.js'
import { startOfLocalDay } from '../scheduling/localDay.js'
import { useDeferralCutoff } from '../scheduling/useDeferralCutoff.js'
import { describeTask } from '../today/labels.js'
import { Button } from '../ui/Button.js'
import { EmptyState } from '../ui/EmptyState.js'
import { useRouter } from '../ui/router.js'
import { computeViewState, ThreeStateView } from '../ui/ThreeStateView.js'
import { UndoToast } from '../ui/UndoToast.js'
import { useUndoToast } from '../ui/useUndoToast.js'
import { LAST_ACTIVITY_SQL, SOMEDAY_SQL } from './taskQueries.js'
import styles from './SomedayRoute.module.css'

interface LastActivityRow {
  readonly last_active_at: number
}

/**
 * Part C5's someday tier: everything set aside — by a fresh start, by
 * triage, or by "let it go" on Revisit. It's out of Today, Revisit, the
 * inbox, and every count; this is where it's searched for and brought
 * back, one at a time, to today or to the inbox.
 *
 * Decision 4: no count of what's in here, anywhere — including this page.
 * Part H1's global search will search these too; until then, this page's
 * search is the way to find one.
 */
export function SomedayRoute() {
  const { navigate } = useRouter()
  const cutoff = useDeferralCutoff()
  const todayStart = startOfLocalDay(cutoff - 1)
  const [search, setSearch] = useState('')
  const ftsQuery = toFtsQuery(search)
  const searchId = useId()

  const tasksQuery = useQuery<SomedayTask>(SOMEDAY_SQL, [cutoff, ftsQuery], {
    tables: ['items', 'task_fields'],
  })
  // Whether anything is in someday at all, regardless of the search — so a
  // search with no hits isn't mistaken for an empty someday.
  const anyQuery = useQuery<SomedayTask>(SOMEDAY_SQL, [cutoff, ''], {
    tables: ['items', 'task_fields'],
  })
  const { data: activity } = useQuery<LastActivityRow>(LAST_ACTIVITY_SQL, [], {
    tables: ['items', 'task_fields'],
  })
  const undo = useUndoToast()

  const header = (
    <header className={styles.header}>
      <h1 className={styles.pageTitle}>Someday</h1>
    </header>
  )

  if (tasksQuery.loading || anyQuery.loading) {
    return (
      <div className={styles.someday} aria-busy="true">
        {header}
      </div>
    )
  }

  const tasks = tasksQuery.data
  const viewState = computeViewState(
    anyQuery.data.length === 0,
    activity.at(0)?.last_active_at ?? null,
  )

  function bringBack(task: SomedayTask, to: BringBackTo): void {
    const plan = planBringBack(task, to, todayStart)
    void dbClient.mutate({ writes: plan.writes })
    undo.show(to === 'today' ? 'Brought back to today' : 'Brought back to the inbox', () => {
      void dbClient.mutate({ writes: plan.undoWrites })
    })
  }

  const body = (
    <>
      <label className={styles.search} htmlFor={searchId}>
        <span className={styles.searchLabel}>Search Someday</span>
        <input
          id={searchId}
          type="search"
          value={search}
          autoComplete="off"
          onChange={(event) => {
            setSearch(event.target.value)
          }}
        />
      </label>
      {tasks.length === 0 ? (
        <p className={styles.noMatch} role="status">
          Nothing in Someday matches &ldquo;{search.trim()}&rdquo;.
        </p>
      ) : (
        <ul className={styles.list}>
          {tasks.map((task) => (
            <SomedayRow
              key={task.id}
              task={task}
              detail={describeTask(task, todayStart)}
              onBringBack={(to) => {
                bringBack(task, to)
              }}
            />
          ))}
        </ul>
      )}
    </>
  )

  return (
    <div className={styles.someday}>
      {header}
      <ThreeStateView
        state={viewState}
        empty={
          <EmptyState
            message="Nothing in Someday. Tasks you set aside — or that a fresh start moves here — wait here, kept and searchable, until you want them back."
            actionLabel="Go to Today"
            onAction={() => {
              navigate('/')
            }}
          />
        }
        cold={
          <>
            <p className={styles.lede}>
              Welcome back. Everything here is set aside on purpose — bring back whatever you want
              to pick up.
            </p>
            {body}
          </>
        }
        loaded={
          <>
            <p className={styles.lede}>
              Set aside, not gone. Out of Today and every list until you bring one back.
            </p>
            {body}
          </>
        }
      />
      <UndoToast pending={undo.pending} onUndo={undo.runUndo} />
    </div>
  )
}

function SomedayRow({
  task,
  detail,
  onBringBack,
}: {
  task: SomedayTask
  detail: string
  onBringBack: (to: BringBackTo) => void
}) {
  const titleId = useId()
  return (
    <li className={styles.row} aria-labelledby={titleId}>
      <span className={styles.text}>
        <span id={titleId} className={styles.title}>
          {task.title}
        </span>
        {detail ? <span className={styles.detail}>{detail}</span> : null}
      </span>
      <span className={styles.actions} role="group" aria-label={`Bring back ${task.title}`}>
        <span className={styles.actionsLabel} aria-hidden="true">
          Bring back to
        </span>
        <Button
          size="sm"
          variant="secondary"
          aria-label={`Bring back to today: ${task.title}`}
          onClick={() => {
            onBringBack('today')
          }}
        >
          Today
        </Button>
        <Button
          size="sm"
          variant="ghost"
          aria-label={`Bring back to the inbox: ${task.title}`}
          onClick={() => {
            onBringBack('inbox')
          }}
        >
          Inbox
        </Button>
      </span>
    </li>
  )
}
