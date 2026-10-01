import { useEffect, useState } from 'react'
import { useRegisterSW } from 'virtual:pwa-register/react'
import styles from './PwaPrompts.module.css'

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>
}

function useInstallPrompt() {
  const [deferredPrompt, setDeferredPrompt] = useState<BeforeInstallPromptEvent | null>(null)

  useEffect(() => {
    const handler = (event: Event) => {
      event.preventDefault()
      setDeferredPrompt(event as BeforeInstallPromptEvent)
    }
    window.addEventListener('beforeinstallprompt', handler)
    return () => {
      window.removeEventListener('beforeinstallprompt', handler)
    }
  }, [])

  const promptInstall = async () => {
    if (!deferredPrompt) return
    await deferredPrompt.prompt()
    await deferredPrompt.userChoice
    setDeferredPrompt(null)
  }

  return { canInstall: deferredPrompt !== null, promptInstall }
}

export function PwaPrompts() {
  const { canInstall, promptInstall } = useInstallPrompt()
  const {
    offlineReady: [offlineReady, setOfflineReady],
    needRefresh: [needRefresh, setNeedRefresh],
    updateServiceWorker,
  } = useRegisterSW({
    onRegisteredSW(_url, registration) {
      registration?.update().catch(() => {
        // Offline or no network — the currently installed service worker stays active.
      })
    },
  })

  const close = () => {
    setOfflineReady(false)
    setNeedRefresh(false)
  }

  const showStatus = offlineReady || needRefresh
  if (!canInstall && !showStatus) return null

  // One stack, so two prompts sit one above the other instead of on top
  // of each other — and a slot above the undo toast, never over it.
  return (
    <div className={styles.stack}>
      {canInstall && (
        <div className={styles.toast} role="status">
          <span className={styles.text}>Install Life Helper for offline, one-tap access.</span>
          <span className={styles.actions}>
            <button type="button" className={styles.primary} onClick={() => void promptInstall()}>
              Install
            </button>
          </span>
        </div>
      )}
      {showStatus && (
        <div className={styles.toast} role="status">
          <span className={styles.text}>
            {needRefresh ? 'A new version is ready.' : 'Life Helper is ready to work offline.'}
          </span>
          <span className={styles.actions}>
            {needRefresh && (
              <button
                type="button"
                className={styles.primary}
                onClick={() => void updateServiceWorker(true)}
              >
                Reload
              </button>
            )}
            <button type="button" onClick={close} aria-label="Dismiss">
              Dismiss
            </button>
          </span>
        </div>
      )}
    </div>
  )
}
