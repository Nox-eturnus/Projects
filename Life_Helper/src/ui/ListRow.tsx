import type { ButtonHTMLAttributes, ReactNode } from 'react'
import styles from './ListRow.module.css'

interface ListRowContentProps {
  title: string
  subtitle?: string
  leading?: ReactNode
  trailing?: ReactNode
}

function ListRowContent({ title, subtitle, leading, trailing }: ListRowContentProps) {
  return (
    <>
      {leading ? <span className={styles.leading}>{leading}</span> : null}
      <span className={styles.text}>
        <span className={styles.title}>{title}</span>
        {subtitle ? <span className={styles.subtitle}>{subtitle}</span> : null}
      </span>
      {trailing ? <span className={styles.trailing}>{trailing}</span> : null}
    </>
  )
}

export interface ListRowProps
  extends
    ListRowContentProps,
    Omit<ButtonHTMLAttributes<HTMLButtonElement>, keyof ListRowContentProps> {
  /** Set false for a row that isn't a button, e.g. a status line with no action. */
  interactive?: boolean
}

export function ListRow({
  title,
  subtitle,
  leading,
  trailing,
  interactive = true,
  className,
  type = 'button',
  ...rest
}: ListRowProps) {
  const classes = [styles.row, interactive ? styles.interactive : '', className]
    .filter(Boolean)
    .join(' ')

  if (!interactive) {
    return (
      <div className={classes}>
        <ListRowContent title={title} subtitle={subtitle} leading={leading} trailing={trailing} />
      </div>
    )
  }

  return (
    <button type={type} className={classes} {...rest}>
      <ListRowContent title={title} subtitle={subtitle} leading={leading} trailing={trailing} />
    </button>
  )
}
