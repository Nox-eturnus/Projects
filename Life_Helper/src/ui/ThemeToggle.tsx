import { useEffect, useState } from 'react'
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

  return (
    <button type="button" className={styles.toggle} onClick={handleClick}>
      Theme: {CHOICE_LABEL[choice]}
    </button>
  )
}
