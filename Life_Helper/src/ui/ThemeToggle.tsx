import { useEffect, useState, type ReactNode } from 'react'
import styles from './ThemeToggle.module.css'

type ThemeChoice = 'system' | 'light' | 'dark'

const STORAGE_KEY = 'life-helper-theme'

function readStoredChoice(): ThemeChoice {
  // localStorage can be unavailable or throw (Safari private browsing, storage
  // disabled by policy) — the toggle should still render and default to system.
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY)
    return stored === 'light' || stored === 'dark' ? stored : 'system'
  } catch {
    return 'system'
  }
}

function persistChoice(choice: ThemeChoice) {
  try {
    window.localStorage.setItem(STORAGE_KEY, choice)
  } catch {
    // Not persisted this session; applyChoice() still updates the live DOM.
  }
}

function applyChoice(choice: ThemeChoice) {
  if (choice === 'system') {
    document.documentElement.removeAttribute('data-theme')
  } else {
    document.documentElement.setAttribute('data-theme', choice)
  }
}

const NEXT_CHOICE: Record<ThemeChoice, ThemeChoice> = {
  system: 'light',
  light: 'dark',
  dark: 'system',
}

const CHOICE_LABEL: Record<ThemeChoice, string> = {
  system: 'System',
  light: 'Light',
  dark: 'Dark',
}

/** Half-filled circle for "follow the system", sun for light, moon for dark. */
const CHOICE_ICON: Record<ThemeChoice, ReactNode> = {
  system: (
    <>
      <circle cx="12" cy="12" r="8" />
      <path d="M12 4a8 8 0 0 1 0 16z" fill="currentColor" />
    </>
  ),
  light: (
    <>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" />
    </>
  ),
  dark: <path d="M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5z" />,
}

/**
 * Cycles system -> light -> dark -> system. Exists so the gallery (and manual
 * QA) can inspect both themes without depending on the OS setting, on top of
 * the automatic prefers-color-scheme default every other view relies on.
 */
export function ThemeToggle() {
  const [choice, setChoice] = useState<ThemeChoice>(() => readStoredChoice())

  useEffect(() => {
    applyChoice(choice)
  }, [choice])

  function handleClick() {
    const next = NEXT_CHOICE[choice]
    setChoice(next)
    persistChoice(next)
  }

  const label = `Theme: ${CHOICE_LABEL[choice]}`
  return (
    <button
      type="button"
      className={styles.toggle}
      onClick={handleClick}
      aria-label={label}
      title={`${label} (click to change)`}
    >
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
        focusable="false"
      >
        {CHOICE_ICON[choice]}
      </svg>
    </button>
  )
}
