import { Button } from './Button'
import styles from './EmptyState.module.css'

export interface EmptyStateProps {
  message: string
  actionLabel: string
  onAction: () => void
}

/** The "empty" leg of Decision 7's three-state contract: explain, offer one action. */
export function EmptyState({ message, actionLabel, onAction }: EmptyStateProps) {
  return (
    <div className={styles.container} role="status">
      <p className={styles.message}>{message}</p>
      <Button onClick={onAction}>{actionLabel}</Button>
    </div>
  )
}
