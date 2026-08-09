import { useState } from 'react'
import { useQuery } from '../db/useQuery.js'
import { Button } from '../ui/Button.js'
import { EmptyState } from '../ui/EmptyState.js'
import { ListRow } from '../ui/ListRow.js'
import { useRouter } from '../ui/router.js'
import { computeViewState, ThreeStateView } from '../ui/ThreeStateView.js'
import { TriageView, type ProjectOption, type TriageItemRow } from './TriageView.js'
import styles from './InboxRoute.module.css'

const INBOX_SQL = `
  SELECT items.id, items.title, items.status, items.created_at,
         task_fields.scheduled_for, task_fields.someday, task_fields.completed_at
  FROM items
  LEFT JOIN task_fields ON task_fields.item_id = items.id
  WHERE items.kind = 'task' AND items.status = 'inbox' AND items.deleted_at IS NULL
  ORDER BY items.created_at DESC
`

const PROJECTS_SQL = `
  SELECT id, title FROM items
  WHERE kind = 'project' AND deleted_at IS NULL
  ORDER BY title
`

/**
 * Part B3's inbox: lists everything with status='inbox', newest first, and
 * is the entry point into the one-item-at-a-time triage ritual (see
 * TriageView.tsx). Nothing here batches or stages — every triage action
 * commits immediately through dbClient.mutate(), the same as capture — so
 * "leaving triage mid-way loses nothing" (Part B3's own Definition of
 * Done) isn't special-cased code, it falls out of not having a draft
 * state to lose.
 */
export function InboxRoute() {
  const [mode, setMode] = useState<'list' | 'triage'>('list')
  const { navigate } = useRouter()
  const { data: items, loading } = useQuery<TriageItemRow>(INBOX_SQL, [], {
    tables: ['items', 'task_fields'],
  })
  const { data: projects } = useQuery<ProjectOption>(PROJECTS_SQL, [], { tables: ['items'] })

  if (mode === 'triage') {
    return (
      <TriageView
        items={items}
        projects={projects}
        onExit={() => {
          setMode('list')
        }}
      />
    )
  }

  const mostRecent = items[0]?.created_at ?? null
  const viewState = computeViewState(items.length === 0, mostRecent)

  return (
    <div className={styles.inbox}>
      <div className={styles.header}>
        <h1 className={styles.pageTitle}>Inbox</h1>
        {items.length > 0 ? (
          <Button
            onClick={() => {
              setMode('triage')
            }}
          >
            Start triage
          </Button>
        ) : null}
      </div>

      <ThreeStateView
        state={loading ? 'loaded' : viewState}
        empty={
          <EmptyState
            message="Inbox zero. Nothing to triage."
            actionLabel="Go to Capture"
            onAction={() => {
              navigate('/capture')
            }}
          />
        }
        cold={<p className={styles.coldMessage}>Welcome back. Here&apos;s what&apos;s waiting.</p>}
        loaded={
          <div className={styles.list}>
            {items.map((item) => (
              <ListRow key={item.id} title={item.title} subtitle="Inbox" interactive={false} />
            ))}
          </div>
        }
      />
    </div>
  )
}
