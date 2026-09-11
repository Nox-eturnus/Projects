/// <reference types="node" />
/**
 * Runs `fn` with the process's local timezone set to `timeZone` (an IANA
 * name), restoring the previous one afterwards. Node re-reads `TZ` when it's
 * assigned at runtime, so `new Date(y, m, d)` and every local-field getter
 * inside `fn` behave exactly as they would on a device in that zone — which
 * is what lets Part C1's DST tests run real transitions rather than mocking
 * `Date`.
 *
 * Synchronous only: a timezone swapped under an awaited callback would leak
 * into whatever else runs while it's suspended.
 */
export function withTimeZone<T>(timeZone: string, fn: () => T): T {
  // Restored by name, not by deleting TZ: Node keeps using the last zone it
  // was given after `delete process.env.TZ`, and an empty string means UTC,
  // so neither gets back to the machine's own zone. Resolving the current
  // zone's name first does, whether or not TZ was set to begin with.
  const previous = Intl.DateTimeFormat().resolvedOptions().timeZone
  process.env.TZ = timeZone
  try {
    return fn()
  } finally {
    process.env.TZ = previous
  }
}
