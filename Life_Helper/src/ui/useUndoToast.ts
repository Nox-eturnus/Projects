import { useCallback, useEffect, useRef, useState } from 'react'

/** Decision 7's undo window — Part B3's "every action is undoable for 10 seconds." */
export const UNDO_WINDOW_MS = 10_000

export interface PendingUndo {
  readonly label: string
  readonly undo: () => void
}

/**
 * State for an `<UndoToast>`: `show()` replaces any toast already showing
 * (only the latest action is undoable) and hides it again after
 * UNDO_WINDOW_MS; `runUndo()` performs the undo and hides it at once.
 * Extracted from Part B3's TriageView so Today's actions get the same
 * behavior rather than a second copy of it.
 */
export function useUndoToast(): {
  pending: PendingUndo | null
  show: (label: string, undo: () => void) => void
  runUndo: () => void
} {
  const [pending, setPending] = useState<PendingUndo | null>(null)
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(
    () => () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current)
    },
    [],
  )

  const show = useCallback((label: string, undo: () => void): void => {
    if (timeoutRef.current) clearTimeout(timeoutRef.current)
    setPending({ label, undo })
    timeoutRef.current = setTimeout(() => {
      setPending(null)
    }, UNDO_WINDOW_MS)
  }, [])

  function runUndo(): void {
    if (!pending) return
    if (timeoutRef.current) clearTimeout(timeoutRef.current)
    pending.undo()
    setPending(null)
  }

  return { pending, show, runUndo }
}
