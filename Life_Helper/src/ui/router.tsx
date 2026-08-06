import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type AnchorHTMLAttributes,
  type MouseEvent,
  type ReactNode,
} from 'react'

/**
 * A minimal History-API router: exact-path matching only, no params, no
 * nesting. Every route the plan lists through Phase G is a flat top-level
 * page (/today, /inbox, /routines, ...), so this is genuinely enough for now
 * rather than a placeholder for something bigger — a real router library is
 * an easy swap later if a route ever needs params or nesting.
 */

interface RouterContextValue {
  path: string
  navigate: (to: string) => void
}

const RouterContext = createContext<RouterContextValue | null>(null)

export function RouterProvider({ children }: { children: ReactNode }) {
  const [path, setPath] = useState(() => window.location.pathname)

  useEffect(() => {
    function handlePopState() {
      setPath(window.location.pathname)
    }
    window.addEventListener('popstate', handlePopState)
    return () => {
      window.removeEventListener('popstate', handlePopState)
    }
  }, [])

  const navigate = useCallback((to: string) => {
    if (to !== window.location.pathname) {
      window.history.pushState(null, '', to)
    }
    setPath(to)
  }, [])

  return <RouterContext.Provider value={{ path, navigate }}>{children}</RouterContext.Provider>
}

export function useRouter(): RouterContextValue {
  const context = useContext(RouterContext)
  if (!context) {
    throw new Error('useRouter must be used within a RouterProvider')
  }
  return context
}

export interface RouteDef {
  path: string
  element: ReactNode
}

export function Routes({ routes, notFound }: { routes: RouteDef[]; notFound: ReactNode }) {
  const { path } = useRouter()
  const match = routes.find((route) => route.path === path)
  return <>{match ? match.element : notFound}</>
}

export interface LinkProps extends AnchorHTMLAttributes<HTMLAnchorElement> {
  to: string
}

/** An <a> with a real href (so open-in-new-tab still works) that navigates in place on a plain click. */
export function Link({ to, onClick, ...rest }: LinkProps) {
  const { navigate } = useRouter()

  function handleClick(event: MouseEvent<HTMLAnchorElement>) {
    onClick?.(event)
    if (event.defaultPrevented || event.button !== 0) return
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return
    event.preventDefault()
    navigate(to)
  }

  return <a href={to} onClick={handleClick} {...rest} />
}
