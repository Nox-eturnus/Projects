import { useState } from 'react'
import { Button } from '../ui/Button'
import { contrastPairs } from '../ui/contrast'
import { EmptyState } from '../ui/EmptyState'
import { Input } from '../ui/Input'
import { ListRow } from '../ui/ListRow'
import { Sheet } from '../ui/Sheet'
import { ThreeStateView, type ViewState } from '../ui/ThreeStateView'
import styles from './GalleryRoute.module.css'

const SWATCH_TOKENS = [
  { name: '--ink', role: 'Primary text' },
  { name: '--ink-secondary', role: 'Secondary text' },
  { name: '--muted-fill / --muted-stroke', role: 'Decoration only, never text' },
  { name: '--accent-fill / --accent-stroke', role: 'Decoration only, never text' },
] as const

/**
 * Renders every Part A4 primitive so both themes and the WCAG AA numbers can
 * be reviewed in one place. Not part of the primary nav's feature set — a
 * permanent design-system reference, same idea as Storybook without the
 * dependency.
 */
export function GalleryRoute() {
  const [sheetOpen, setSheetOpen] = useState(false)
  const [threeState, setThreeState] = useState<ViewState>('loaded')

  return (
    <div className={styles.gallery}>
      <h1 className={styles.pageTitle}>Component gallery</h1>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>Buttons</h2>
        <div className={styles.row}>
          <Button variant="primary">Primary</Button>
          <Button variant="secondary">Secondary</Button>
          <Button variant="ghost">Ghost</Button>
          <Button variant="primary" size="sm">
            Primary sm
          </Button>
          <Button variant="primary" disabled>
            Disabled
          </Button>
        </div>
      </section>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>Inputs</h2>
        <div className={styles.column}>
          <Input label="Title" placeholder="Buy milk" />
          <Input label="Title" defaultValue="Buy milk" error="Title is required" />
        </div>
      </section>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>List rows</h2>
        <div className={styles.list}>
          <ListRow title="Buy milk" subtitle="Inbox" onClick={() => undefined} />
          <ListRow title="Renew passport" subtitle="Due in 3 days" onClick={() => undefined} />
          <ListRow title="Read-only row" interactive={false} />
        </div>
      </section>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>Sheet</h2>
        <Button
          onClick={() => {
            setSheetOpen(true)
          }}
        >
          Open sheet
        </Button>
        <Sheet
          open={sheetOpen}
          onClose={() => {
            setSheetOpen(false)
          }}
          title="Move to project"
        >
          <p>Sheet content goes here.</p>
        </Sheet>
      </section>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>Three-state view (Decision 7)</h2>
        <div className={styles.row}>
          <Button
            variant={threeState === 'empty' ? 'primary' : 'secondary'}
            size="sm"
            onClick={() => {
              setThreeState('empty')
            }}
          >
            Empty
          </Button>
          <Button
            variant={threeState === 'cold' ? 'primary' : 'secondary'}
            size="sm"
            onClick={() => {
              setThreeState('cold')
            }}
          >
            Cold
          </Button>
          <Button
            variant={threeState === 'loaded' ? 'primary' : 'secondary'}
            size="sm"
            onClick={() => {
              setThreeState('loaded')
            }}
          >
            Loaded
          </Button>
        </div>
        <div className={styles.demoFrame}>
          <ThreeStateView
            state={threeState}
            empty={
              <EmptyState
                message="No tasks yet."
                actionLabel="Capture a task"
                onAction={() => undefined}
              />
            }
            cold={<p>Welcome back. Here&apos;s where things stand — no counts, no catching up.</p>}
            loaded={<ListRow title="Buy milk" subtitle="Inbox" onClick={() => undefined} />}
          />
        </div>
      </section>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>Color tokens and measured contrast</h2>
        <div className={styles.swatchGrid}>
          {SWATCH_TOKENS.map((token) => (
            <div key={token.name} className={styles.swatch}>
              <span className={styles.swatchName}>{token.name}</span>
              <span className={styles.swatchRole}>{token.role}</span>
            </div>
          ))}
        </div>
        <div className={styles.tableScroll}>
          <table className={styles.contrastTable}>
            <thead>
              <tr>
                <th>Pair</th>
                <th>Theme</th>
                <th>Ratio</th>
                <th>AA (text)</th>
              </tr>
            </thead>
            <tbody>
              {contrastPairs.map((pair) => (
                <tr key={`${pair.theme}-${pair.label}`}>
                  <td>{pair.label}</td>
                  <td>{pair.theme}</td>
                  <td>{pair.ratio.toFixed(2)}:1</td>
                  <td>{pair.requiredForText ? (pair.ratio >= 4.5 ? 'pass' : 'FAIL') : 'n/a'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}
