import { useEffect } from 'react'
import { useRouter } from '../ui/router.js'

export const CAPTURE_PATH = '/capture'

/** Dispatched instead of navigating when Ctrl/Cmd+K fires while already on
 * the capture route, so the shortcut still does something useful (refocus
 * the input) rather than a same-path navigate() no-op. */
export const FOCUS_CAPTURE_EVENT = 'life-helper:focus-capture'

function isCaptureChord(event: KeyboardEvent): boolean {
  return (event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k'
}

/**
 * Binds Ctrl/Cmd+K to open capture from anywhere in the app (Part B1). Must
 * be mounted once under RouterProvider — see AppRoutes in App.tsx.
 */
export function useGlobalCaptureShortcut(): void {
  const { navigate } = useRouter()

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent): void {
      if (!isCaptureChord(event)) return
      event.preventDefault()
      if (window.location.pathname === CAPTURE_PATH) {
        window.dispatchEvent(new Event(FOCUS_CAPTURE_EVENT))
      } else {
        navigate(CAPTURE_PATH)
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => {
      window.removeEventListener('keydown', handleKeyDown)
    }
  }, [navigate])
}
