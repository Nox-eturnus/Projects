import { Button } from './Button'
import type { PendingUndo } from './useUndoToast'
import styles from './UndoToast.module.css'

/** The toast half of useUndoToast(): the last action's label and an Undo button. */
export function UndoToast({
  pending,
  onUndo,
}: {
  pending: PendingUndo | null
  onUndo: () => void
}) {
  if (!pending) return null
  return (
    <div className={styles.toast} role="status">
      <span>{pending.label}</span>
      <Button variant="ghost" size="sm" onClick={onUndo}>
        Undo
      </Button>
    </div>
  )
}
