import { useCallback, useEffect, useRef, useState, type PointerEvent } from 'react'
import { planTriageAction, type TriageAction, type TriageItem } from '../triage/triageActions.js'
import { dbClient } from '../db/client.js'
import type { Write } from '../db/ops.js'
import { Button } from '../ui/Button.js'
import { EmptyState } from '../ui/EmptyState.js'
import { ListRow } from '../ui/ListRow.js'
import { Sheet } from '../ui/Sheet.js'
import styles from './TriageView.module.css'

export interface TriageItemRow {
  readonly id: string
  readonly title: string
  readonly status: string | null
  readonly created_at: number
  readonly scheduled_for: number | null
  readonly someday: number
  readonly completed_at: number | null
}

export interface ProjectOption {
  readonly id: string
  readonly title: string
}

export interface TriageViewProps {
  readonly items: readonly TriageItemRow[]
  readonly projects: readonly ProjectOption[]
  readonly onExit: () => void
}

// Decision 7's undo window, applied to every triage action per Part B3's
// own Definition of Done ("every action is undoable for 10 seconds").
const UNDO_WINDOW_MS = 10_000
const SWIPE_THRESHOLD_PX = 80

function todayInputValue(): string {
  const d = new Date()
  return `${d.getFullYear().toString().padStart(4, '0')}-${(d.getMonth() + 1).toString().padStart(2, '0')}-${d.getDate().toString().padStart(2, '0')}`
}

interface UndoState {
  readonly label: string
  readonly writes: readonly Write[]
}

/**
 * The one-item-at-a-time triage ritual (Part B3). Every action commits
 * immediately through dbClient.mutate() — nothing here batches or stages
 * — so navigating away mid-triage never loses anything; the remaining
 * inbox items are simply however far triage got. `items` is the live,
 * reactive inbox query from InboxRoute: an applied action changes the
 * current item's status/kind, the query re-runs, and the next item
 * becomes `items[0]` for free — no local index to manage.
 *
 * Keyboard: T today, D date, P project, N note, R routine, S someday,
 * Enter done, Backspace/Delete delete — all single-key, disabled while a
 * Sheet is open so typing in the date picker doesn't trigger an action.
 * Touch: swipe right on the card = done, swipe left = someday; the other
 * six actions are always reachable as buttons too, since a swipe-only
 * interface would hide most of them from mobile users entirely.
 */
export function TriageView({ items, projects, onExit }: TriageViewProps) {
  const [undoState, setUndoState] = useState<UndoState | null>(null)
  const [dateSheetOpen, setDateSheetOpen] = useState(false)
  const [projectSheetOpen, setProjectSheetOpen] = useState(false)
  const [dateValue, setDateValue] = useState(todayInputValue)
  const undoTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const swipeStartXRef = useRef<number | null>(null)

  useEffect(
    () => () => {
      if (undoTimeoutRef.current) clearTimeout(undoTimeoutRef.current)
    },
    [],
  )

  const showUndo = useCallback((label: string, writes: readonly Write[]): void => {
    if (undoTimeoutRef.current) clearTimeout(undoTimeoutRef.current)
    setUndoState({ label, writes })
    undoTimeoutRef.current = setTimeout(() => {
      setUndoState(null)
    }, UNDO_WINDOW_MS)
  }, [])

  // Guards on items.length rather than `items[0]`'s own truthiness: this
  // project's tsconfig doesn't set noUncheckedIndexedAccess, so TS infers
  // a plain index access as always-defined and flags an `if (!x)` check on
  // it as dead code — even though items[0] is genuinely undefined once the
  // inbox empties out. Checking the array's length first sidesteps that
  // entirely, and lets every `items[0]` after the check type as plain
  // TriageItemRow with no cast needed.
  //
  // Memoized (not a plain function) so the keydown-binding effect below
  // doesn't re-subscribe its window listener on every render — only when
  // `items` (or `showUndo`, itself stable) actually changes.
  const apply = useCallback(
    (action: TriageAction): void => {
      if (items.length === 0) return
      const row = items[0]
      const item: TriageItem = {
        id: row.id,
        status: row.status,
        scheduledFor: row.scheduled_for,
        someday: row.someday,
        completedAt: row.completed_at,
      }
      const plan = planTriageAction(item, action, Date.now())
      void dbClient.mutate({ writes: plan.writes })
      showUndo(plan.label, plan.undoWrites)
    },
    [items, showUndo],
  )

  function handleUndo(): void {
    if (!undoState) return
    if (undoTimeoutRef.current) clearTimeout(undoTimeoutRef.current)
    void dbClient.mutate({ writes: undoState.writes })
    setUndoState(null)
  }

  useEffect(() => {
    if (dateSheetOpen || projectSheetOpen || items.length === 0) return
    function handleKeyDown(event: KeyboardEvent): void {
      switch (event.key) {
        case 't':
        case 'T':
          apply({ type: 'scheduleToday' })
          return
        case 'd':
        case 'D':
          setDateSheetOpen(true)
          return
        case 'p':
        case 'P':
          setProjectSheetOpen(true)
          return
        case 'n':
        case 'N':
          apply({ type: 'convertToNote' })
          return
        case 'r':
        case 'R':
          apply({ type: 'convertToRoutine' })
          return
        case 's':
        case 'S':
          apply({ type: 'someday' })
          return
        case 'Enter':
          apply({ type: 'done' })
          return
        case 'Backspace':
        case 'Delete':
          apply({ type: 'delete' })
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => {
      window.removeEventListener('keydown', handleKeyDown)
    }
  }, [items, dateSheetOpen, projectSheetOpen, apply])

  function confirmDate(): void {
    if (!dateValue) return
    const [year, month, day] = dateValue.split('-').map(Number)
    setDateSheetOpen(false)
    apply({ type: 'scheduleDate', date: new Date(year, month - 1, day).getTime() })
  }

  function handlePointerDown(event: PointerEvent<HTMLDivElement>): void {
    swipeStartXRef.current = event.clientX
  }

  function handlePointerUp(event: PointerEvent<HTMLDivElement>): void {
    const start = swipeStartXRef.current
    swipeStartXRef.current = null
    if (start === null) return
    const delta = event.clientX - start
    if (delta > SWIPE_THRESHOLD_PX) apply({ type: 'done' })
    else if (delta < -SWIPE_THRESHOLD_PX) apply({ type: 'someday' })
  }

  // Shared between both branches below: the toast for the item that was
  // *just* triaged must keep showing even once triaging it emptied the
  // inbox — the empty-state branch used to skip it entirely, which meant
  // the last item of a session had no undo option at all. Caught by
  // e2e/triage.spec.ts, not reasoned about in advance.
  const undoToast = undoState ? (
    <div className={styles.toast} role="status">
      <span>{undoState.label}</span>
      <Button variant="ghost" size="sm" onClick={handleUndo}>
        Undo
      </Button>
    </div>
  ) : null

  if (items.length === 0) {
    return (
      <div className={styles.triage}>
        <EmptyState
          message="Inbox zero. Nice work."
          actionLabel="Back to inbox"
          onAction={onExit}
        />
        {undoToast}
      </div>
    )
  }
  const current = items[0]

  return (
    <div className={styles.triage}>
      <div className={styles.triageHeader}>
        <span className={styles.progress}>
          {items.length} {items.length === 1 ? 'item' : 'items'} left
        </span>
        <Button variant="ghost" size="sm" onClick={onExit}>
          Exit triage
        </Button>
      </div>

      <div className={styles.card} onPointerDown={handlePointerDown} onPointerUp={handlePointerUp}>
        <h1 className={styles.itemTitle}>{current.title}</h1>
      </div>

      <div className={styles.actions}>
        <Button
          onClick={() => {
            apply({ type: 'scheduleToday' })
          }}
        >
          Today <kbd>T</kbd>
        </Button>
        <Button
          onClick={() => {
            setDateSheetOpen(true)
          }}
        >
          Date <kbd>D</kbd>
        </Button>
        <Button
          onClick={() => {
            setProjectSheetOpen(true)
          }}
        >
          Project <kbd>P</kbd>
        </Button>
        <Button
          onClick={() => {
            apply({ type: 'convertToNote' })
          }}
        >
          Note <kbd>N</kbd>
        </Button>
        <Button
          onClick={() => {
            apply({ type: 'convertToRoutine' })
          }}
        >
          Routine <kbd>R</kbd>
        </Button>
        <Button
          onClick={() => {
            apply({ type: 'someday' })
          }}
        >
          Someday <kbd>S</kbd>
        </Button>
        <Button
          onClick={() => {
            apply({ type: 'done' })
          }}
        >
          Done <kbd>Enter</kbd>
        </Button>
        <Button
          variant="secondary"
          onClick={() => {
            apply({ type: 'delete' })
          }}
        >
          Delete <kbd>Del</kbd>
        </Button>
      </div>

      <Sheet
        open={dateSheetOpen}
        onClose={() => {
          setDateSheetOpen(false)
        }}
        title="Schedule for a date"
      >
        <div className={styles.dateSheetBody}>
          <input
            type="date"
            aria-label="Date"
            value={dateValue}
            onChange={(event) => {
              setDateValue(event.target.value)
            }}
          />
          <Button onClick={confirmDate}>Set date</Button>
        </div>
      </Sheet>

      <Sheet
        open={projectSheetOpen}
        onClose={() => {
          setProjectSheetOpen(false)
        }}
        title="File to project"
      >
        {projects.length === 0 ? (
          <p className={styles.noProjects}>No projects yet.</p>
        ) : (
          <div className={styles.projectList}>
            {projects.map((project) => (
              <ListRow
                key={project.id}
                title={project.title}
                onClick={() => {
                  setProjectSheetOpen(false)
                  apply({
                    type: 'fileToProject',
                    projectId: project.id,
                    projectTitle: project.title,
                  })
                }}
              />
            ))}
          </div>
        )}
      </Sheet>

      {undoToast}
    </div>
  )
}
