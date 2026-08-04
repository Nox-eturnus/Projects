import { useEffect, useState } from 'react'
import { dbClient } from './client.js'
import type { TableName } from './ops.js'

export interface UseQueryResult<T> {
  readonly data: T[]
  readonly loading: boolean
  readonly error: Error | null
}

/**
 * Re-runs `sql` whenever a mutate() call touches one of `tables` — in this
 * tab or another, since dbClient.subscribe() fires from both the local
 * leader worker and the cross-tab BroadcastChannel relay (see client.ts).
 * The caller declares its dependencies explicitly rather than this hook
 * parsing `sql` to infer them, which keeps the dependency tracking exact
 * and the query itself just plain SQL.
 */
export function useQuery<T = Record<string, unknown>>(
  sql: string,
  params: readonly unknown[],
  options: { readonly tables: readonly TableName[] },
): UseQueryResult<T> {
  const paramsKey = JSON.stringify(params)
  const tablesKey = options.tables.join(',')

  const [state, setState] = useState<UseQueryResult<T>>({ data: [], loading: true, error: null })

  useEffect(() => {
    let cancelled = false
    const parsedParams = JSON.parse(paramsKey) as unknown[]
    const dependentTables = tablesKey.length > 0 ? tablesKey.split(',') : []

    function run(): void {
      dbClient
        .query<T>(sql, parsedParams)
        .then((data) => {
          if (!cancelled) setState({ data, loading: false, error: null })
        })
        .catch((error: unknown) => {
          if (!cancelled) {
            setState((prev) => ({
              data: prev.data,
              loading: false,
              error: error instanceof Error ? error : new Error(String(error)),
            }))
          }
        })
    }

    run()
    const unsubscribe = dbClient.subscribe((touchedTables) => {
      if (touchedTables.some((table) => dependentTables.includes(table))) run()
    })

    return () => {
      cancelled = true
      unsubscribe()
    }
  }, [sql, paramsKey, tablesKey])

  return state
}
