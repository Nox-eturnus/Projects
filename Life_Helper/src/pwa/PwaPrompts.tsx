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

  return (
    <>
      {canInstall && (
        <div className={styles.toast} role="status">
          <span>Install Life Helper for offline, one-tap access.</span>
          <button type="button" onClick={() => void promptInstall()}>
            Install
          </button>
        </div>
      )}
      {(offlineReady || needRefresh) && (
        <div className={styles.toast} role="status">
          <span>
            {needRefresh ? 'A new version is ready.' : 'Life Helper is ready to work offline.'}
          </span>
          {needRefresh && (
            <button type="button" onClick={() => void updateServiceWorker(true)}>
              Reload
            </button>
          )}
          <button type="button" onClick={close} aria-label="Dismiss">
            Dismiss
          </button>
        </div>
      )}
    </>
  )
}
