import { useEffect } from 'react'
import { deviceInfo, recordColdStart, recordOpen } from './gateLog.js'

// Where this page load started, read once when the app's code first runs.
// A cold start to Today is a load that began on Today — not a later
// in-app navigation to it, which doesn't load anything from scratch.
const bootPath = typeof window === 'undefined' ? '' : window.location.pathname
let coldStartTaken = false

/**
 * Part C6's "Today renders in under 1.5s cold start." Called by Today with
 * `ready` once its data has loaded and rendered; records, once per page
 * load, the time from navigation start (`performance.now()`'s origin) to
 * the next frame — so it covers fetching the app, starting SQLite on OPFS,
 * running Today's queries, and painting the result. A back/forward
 * restore from the browser's cache isn't a cold start, so it's skipped.
 */
export function useRecordColdStart(ready: boolean): void {
  useEffect(() => {
    if (!ready || coldStartTaken) return
    coldStartTaken = true
    if (bootPath !== '/') return
    const navigation = performance.getEntriesByType('navigation').at(0) as
      PerformanceNavigationTiming | undefined
    if (navigation?.type === 'back_forward') return
    requestAnimationFrame(() => {
      recordColdStart({
        at: Date.now(),
        ms: Math.round(performance.now()),
        android: deviceInfo().android,
      })
    })
  }, [ready])
}

/**
 * Records each day the app is opened — on launch, and whenever it comes
 * back to the foreground (an installed app is often resumed, not
 * relaunched). Once per day; nothing else is kept.
 */
export function useRecordOpens(): void {
  useEffect(() => {
    recordOpen(Date.now())
    function onVisibility(): void {
      if (document.visibilityState === 'visible') recordOpen(Date.now())
    }
    document.addEventListener('visibilitychange', onVisibility)
    return () => {
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [])
}
