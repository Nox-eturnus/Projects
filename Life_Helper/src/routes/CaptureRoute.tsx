import { useEffect, useRef, useState, type KeyboardEvent } from 'react'
import { captureTask } from '../capture/captureTask.js'
import { FOCUS_CAPTURE_EVENT } from '../capture/useGlobalCaptureShortcut.js'
import { dbClient } from '../db/client.js'
import { useQuery } from '../db/useQuery.js'
import { EmptyState } from '../ui/EmptyState.js'
import { ListRow } from '../ui/ListRow.js'
import { computeViewState, ThreeStateView } from '../ui/ThreeStateView.js'
import styles from './CaptureRoute.module.css'

interface RecentCapture {
  id: string
  title: string
  created_at: number
}

const RECENT_CAPTURES_SQL = `
  SELECT id, title, created_at FROM items
  WHERE kind = 'task' AND status = 'inbox' AND deleted_at IS NULL
  ORDER BY created_at DESC
  LIMIT 5
`

/**
 * Part B1's capture surface. Decision 3: exactly one required field (the
 * raw text), no modal, no confirmation, no network round trip. Enter
 * submits; Shift+Enter inserts a newline; the input stays focused across
 * consecutive captures rather than blurring after submit.
 */
export function CaptureRoute() {
  const [text, setText] = useState('')
  // TEMPORARY — Part B1's Android device verification only. Decision 9's
  // "keypress to persisted < 200ms" budget needs an on-device number, and
  // this is the cheapest way to read one off a phone screen with no
  // laptop/remote-debugging tether. Remove this state, the timing in
  // handleKeyDown, and the <p> below once that number is recorded in
  // docs/phase_B1_capture_surface.md.
  const [lastLatencyMs, setLastLatencyMs] = useState<number | null>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const { data, loading } = useQuery<RecentCapture>(RECENT_CAPTURES_SQL, [], {
    tables: ['items'],
  })

  useEffect(() => {
    textareaRef.current?.focus()
    function handleFocusRequest(): void {
      textareaRef.current?.focus()
    }
    window.addEventListener(FOCUS_CAPTURE_EVENT, handleFocusRequest)
    return () => {
      window.removeEventListener(FOCUS_CAPTURE_EVENT, handleFocusRequest)
    }
  }, [])

  // Clears (and keeps focus in) the field the instant Enter is pressed,
  // without waiting for the write to finish — Decision 3 says capture must
  // never block, and that includes never disabling the field while its
  // write is in flight. captureTask() itself still trims/validates; a
  // blank submit is simply a no-op that leaves the field as-is.
  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>): void {
    if (event.key !== 'Enter' || event.shiftKey || event.nativeEvent.isComposing) return
    event.preventDefault()
    const raw = text
    if (raw.trim().length === 0) return
    setText('')
    // Timed from this same keydown, not from an earlier keystroke — this is
    // the "commit" half of Decision 9's budget (write durably persisted),
    // not the full first-character-to-here typing latency, which is the
    // browser's own input handling and not something this write path
    // controls.
    const start = performance.now()
    void captureTask(raw, { mutate: (input) => dbClient.mutate(input) }).then(() => {
      setLastLatencyMs(Math.round(performance.now() - start))
    })
  }

  function handleMicClick(): void {
    // No speech recognition here by design (Decision 5's "deterministic
    // first" cousin for capture itself): focusing the field is all that's
    // needed to bring up the system keyboard, whose own dictation button
    // Android already provides for free.
    textareaRef.current?.focus()
  }

  const mostRecent = data[0]?.created_at ?? null
  const viewState = computeViewState(data.length === 0, mostRecent)

  return (
    <div className={styles.capture}>
      <h1 className={styles.pageTitle}>Capture</h1>

      <div className={styles.inputRow}>
        <textarea
          ref={textareaRef}
          className={styles.textarea}
          aria-label="Capture"
          placeholder="Type anything — cleanup happens later."
          value={text}
          onChange={(event) => {
            setText(event.target.value)
          }}
          onKeyDown={handleKeyDown}
          enterKeyHint="done"
          rows={2}
        />
        <button
          type="button"
          className={styles.micButton}
          aria-label="Dictate with the system keyboard"
          onClick={handleMicClick}
        >
          <span aria-hidden="true">🎤</span>
        </button>
      </div>

      {lastLatencyMs !== null ? (
        // TEMPORARY — see the note at lastLatencyMs's declaration above.
        <p className={styles.latencyDebug}>Captured in {lastLatencyMs}ms</p>
      ) : null}

      <section className={styles.recent}>
        <h2 className={styles.sectionTitle}>Recently captured</h2>
        <ThreeStateView
          state={loading ? 'loaded' : viewState}
          empty={
            <EmptyState
              message="Nothing captured yet. Type above and press Enter to add your first item."
              actionLabel="Focus capture"
              onAction={() => textareaRef.current?.focus()}
            />
          }
          cold={<p className={styles.coldMessage}>Welcome back. New captures will show up here.</p>}
          loaded={
            <div className={styles.list}>
              {data.map((item) => (
                <ListRow key={item.id} title={item.title} subtitle="Inbox" interactive={false} />
              ))}
            </div>
          }
        />
      </section>
    </div>
  )
}
