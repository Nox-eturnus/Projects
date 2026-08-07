import type { ReactNode } from 'react'
import { Link, useRouter } from './router'
import { ThemeToggle } from './ThemeToggle'
import styles from './AppShell.module.css'

export interface NavItem {
  to: string
  label: string
}

export const NAV_ITEMS: NavItem[] = [
  { to: '/', label: 'Today' },
  { to: '/capture', label: 'Capture' },
  { to: '/gallery', label: 'Gallery' },
]

export function AppShell({ children }: { children: ReactNode }) {
  const { path } = useRouter()

  return (
    <div className={styles.shell}>
      <a className={styles.skipLink} href="#main-content">
        Skip to content
      </a>
      <header className={styles.header}>
        <span className={styles.brand}>Life Helper</span>
        <ThemeToggle />
      </header>
      <nav className={styles.nav} aria-label="Primary">
        <ul className={styles.navList}>
          {NAV_ITEMS.map((item) => {
            const isCurrent = path === item.to
            return (
              <li key={item.to}>
                <Link
                  to={item.to}
                  className={styles.navLink}
                  aria-current={isCurrent ? 'page' : undefined}
                  data-current={isCurrent || undefined}
                >
                  {item.label}
                </Link>
              </li>
            )
          })}
        </ul>
      </nav>
      <main id="main-content" className={styles.main}>
        {children}
      </main>
    </div>
  )
}
