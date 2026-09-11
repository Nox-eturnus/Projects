import { useState } from 'react'
import styles from './TaskCheck.module.css'

export interface TaskCheckProps {
  readonly title: string
  readonly detail?: string
  readonly done: boolean
  readonly onToggle: (done: boolean) => void
  /** 'prominent' for Today's top 3; 'plain' for everything below it. */
  readonly emphasis?: 'prominent' | 'plain'
}

/**
 * A task with a real checkbox — a native `<input type="checkbox">` in a
 * `<label>`, so the whole row is the hit target, Space toggles it, and a
 * screen reader announces "checkbox, checked" without any ARIA of our own.
 * Done is shown by a strike-through *and* the checked box, never by colour
 * alone (Decision 13).
 *
 * The tick shows the instant it's tapped. `done` comes from the database,
 * which only catches up after the write and the re-query — so a tap is
 * remembered as an override, together with the `done` it was made
 * against. The moment `done` moves off that value (the database caught
 * up, or something else changed it), the override is dropped for good —
 * not merely ignored, or a later undo that happens to restore the old
 * value would bring a stale tick back with it.
 */
export function TaskCheck({ title, detail, done, onToggle, emphasis = 'plain' }: TaskCheckProps) {
  const [tapped, setTapped] = useState<{ value: boolean; against: boolean } | null>(null)
  // React's "adjust state while rendering" pattern: re-renders immediately,
  // before anything is painted with the stale override.
  if (tapped !== null && tapped.against !== done) setTapped(null)
  const shown = tapped !== null && tapped.against === done ? tapped.value : done

  return (
    <label className={`${styles.row} ${styles[emphasis]}`} data-done={shown || undefined}>
      <input
        type="checkbox"
        className={styles.box}
        checked={shown}
        onChange={(event) => {
          setTapped({ value: event.target.checked, against: done })
          onToggle(event.target.checked)
        }}
      />
      <span className={styles.text}>
        <span className={styles.title}>{title}</span>
        {detail ? <span className={styles.detail}>{detail}</span> : null}
      </span>
    </label>
  )
}
