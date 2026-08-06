import { useEffect, useId, useRef, type MouseEvent, type ReactNode } from 'react'
import styles from './Sheet.module.css'

export interface SheetProps {
  open: boolean
  onClose: () => void
  title: string
  children: ReactNode
}

/**
 * A native <dialog>, not a hand-rolled overlay: focus trapping, Esc-to-close,
 * and top-layer stacking come from the browser for free.
 */
export function Sheet({ open, onClose, title, children }: SheetProps) {
  const dialogRef = useRef<HTMLDialogElement>(null)
  const titleId = useId()

  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return
    // jsdom (unit tests) has no HTMLDialogElement.showModal/close at all, unlike
    // real browsers — lib.dom.d.ts types them as always present, so the optional
    // chain below is only "unnecessary" from TS's point of view, not jsdom's.
    if (open && !dialog.open) {
      // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition
      dialog.showModal?.()
    } else if (!open && dialog.open) {
      // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition
      dialog.close?.()
    }
  }, [open])

  function handleBackdropClick(event: MouseEvent<HTMLDialogElement>) {
    if (event.target === dialogRef.current) {
      onClose()
    }
  }

  return (
    <dialog
      ref={dialogRef}
      className={styles.sheet}
      aria-labelledby={titleId}
      onClose={onClose}
      onCancel={onClose}
      onClick={handleBackdropClick}
    >
      <div className={styles.header}>
        <h2 id={titleId} className={styles.title}>
          {title}
        </h2>
        <button type="button" className={styles.close} onClick={onClose} aria-label="Close">
          &times;
        </button>
      </div>
      <div className={styles.body}>{children}</div>
    </dialog>
  )
}
