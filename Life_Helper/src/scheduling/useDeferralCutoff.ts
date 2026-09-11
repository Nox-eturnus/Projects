import { useEffect, useState } from 'react'
import { deferralCutoff } from './schedule.js'

/**
 * The `deferralCutoff()` to bind to `NOT_DEFERRED_SQL` in a view's query.
 * It only changes at local midnight, so it's a stable useQuery() param all
 * day — and it does change then: a task deferred to tomorrow appears at
 * midnight even if the app has been open since before it, without waiting
 * for some unrelated write to re-run the query.
 */
export function useDeferralCutoff(): number {
  const [cutoff, setCutoff] = useState(() => deferralCutoff(Date.now()))

  useEffect(() => {
    const timeout = setTimeout(
      () => {
        // max() so a timer that fires a hair early (a clock adjustment,
        // say) still advances to the next day rather than recomputing the
        // same cutoff, which would leave no further timer scheduled.
        setCutoff(deferralCutoff(Math.max(Date.now(), cutoff)))
      },
      Math.max(0, cutoff - Date.now()),
    )
    return () => {
      clearTimeout(timeout)
    }
  }, [cutoff])

  return cutoff
}
