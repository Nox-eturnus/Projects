import type { ReactNode } from 'react'

export type ViewState = 'empty' | 'cold' | 'loaded'

export interface ThreeStateViewProps {
  state: ViewState
  /** No data yet — explain what would appear here and offer one action. */
  empty: ReactNode
  /**
   * The user has been away 3+ days. Must not display red badges, overdue
   * counts, or guilt language (Decision 7) — reviewed per view, not enforced
   * by this component itself.
   */
  cold: ReactNode
  loaded: ReactNode
}

/**
 * The reusable contract from Decision 7: a view is not done until it supplies
 * all three states. Requiring `empty`/`cold`/`loaded` as required props (not
 * optional ones defaulting to `loaded`) is what makes skipping one a
 * compile-time error instead of something a future view can quietly forget.
 */
export function ThreeStateView({ state, empty, cold, loaded }: ThreeStateViewProps) {
  switch (state) {
    case 'empty':
      return <>{empty}</>
    case 'cold':
      return <>{cold}</>
    case 'loaded':
      return <>{loaded}</>
  }
}

/** Decision 7's "3+ days" absence threshold, shared so every view agrees on it. */
export const COLD_AFTER_MS = 3 * 24 * 60 * 60 * 1000

export function computeViewState(
  isEmpty: boolean,
  lastActiveAt: number | null,
  now: number = Date.now(),
): ViewState {
  if (isEmpty) return 'empty'
  if (lastActiveAt !== null && now - lastActiveAt >= COLD_AFTER_MS) return 'cold'
  return 'loaded'
}
