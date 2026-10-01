import { useEffect, useState } from 'react'

/**
 * The current time, re-read every `stepMs` while the page is mounted — for
 * displays that count down with the day ("about 3h free"). This only
 * re-renders; it never touches the network, so it isn't the kind of
 * background timer Part C3 rules out for calendar polling. Browsers
 * throttle it in a hidden tab, which is fine: nobody's looking.
 */
export function useNow(stepMs = 60_000): number {
  const [now, setNow] = useState(Date.now)
  useEffect(() => {
    const interval = setInterval(() => {
      setNow(Date.now())
    }, stepMs)
    return () => {
      clearInterval(interval)
    }
  }, [stepMs])
  return now
}
