import type { ReactNode } from 'react'
import { Link, useRouter } from './router'
import { ThemeToggle } from './ThemeToggle'
import styles from './AppShell.module.css'

export type NavIcon = 'today' | 'capture' | 'inbox' | 'revisit' | 'settings'

export interface NavItem {
  to: string
  label: string
  icon: NavIcon
}

// The gallery (and its ops replay check) is a tool, not a daily
// destination: it's linked from Settings rather than taking a tab.
export const NAV_ITEMS: NavItem[] = [
  { to: '/', label: 'Today', icon: 'today' },
  { to: '/capture', label: 'Capture', icon: 'capture' },
  { to: '/inbox', label: 'Inbox', icon: 'inbox' },
  { to: '/revisit', label: 'Revisit', icon: 'revisit' },
  { to: '/settings', label: 'Settings', icon: 'settings' },
]

/** 24px line icons; the label beside each carries the meaning. */
const ICON_PATHS: Record<NavIcon, ReactNode> = {
  today: (
    <>
      <rect x="3.5" y="5" width="17" height="15" rx="2" />
      <path d="M3.5 10h17M8 3v4M16 3v4" />
      <circle cx="12" cy="15" r="1.5" fill="currentColor" />
    </>
  ),
  capture: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 8v8M8 12h8" />
    </>
  ),
  inbox: (
    <>
      <path d="M3 13h5l1.5 3h5L16 13h5" />
      <path d="M5.5 5h13L21 13v5a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1v-5z" />
    </>
  ),
  revisit: (
    <>
      <path d="M20 11a8 8 0 1 0-2.34 5.66" />
      <path d="M20 4v7h-7" />
    </>
  ),
  settings: (
    <>
      <path d="M4 7h10M18 7h2M4 17h4M12 17h8" />
      <circle cx="16" cy="7" r="2" />
      <circle cx="10" cy="17" r="2" />
    </>
  ),
}

function Icon({ name }: { name: NavIcon }) {
  return (
    <svg
      className={styles.navIcon}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {ICON_PATHS[name]}
    </svg>
  )
}

export function AppShell({ children }: { children: ReactNode }) {
  const { path } = useRouter()

  return (
    <div className={styles.shell}>
      <a className={styles.skipLink} href="#main-content">
        Skip to content
      </a>
      <div className={styles.sidebar}>
        <header className={styles.header}>
          <span className={styles.brand}>
            <img className={styles.brandMark} src="/pwa-192x192.png" alt="" />
            Life Helper
          </span>
          <ThemeToggle />
        </header>
        <nav className={styles.nav} aria-label="Primary">
          <ul className={styles.navList}>
            {NAV_ITEMS.map((item) => {
              const isCurrent = path === item.to
              return (
                <li key={item.to} className={styles.navItem}>
                  <Link
                    to={item.to}
                    className={styles.navLink}
                    aria-current={isCurrent ? 'page' : undefined}
                    data-current={isCurrent || undefined}
                  >
                    <Icon name={item.icon} />
                    <span>{item.label}</span>
                  </Link>
                </li>
              )
            })}
          </ul>
        </nav>
      </div>
      <main id="main-content" className={styles.main}>
        <div className={styles.content}>{children}</div>
      </main>
    </div>
  )
}
