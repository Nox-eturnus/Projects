import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react'
import { captureTask } from '../capture/captureTask.js'
import { parse, resolveCapture, tokenKey } from '../capture/parse.js'
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
 * Part B1's capture surface, extended by Part B2's deterministic parser.
 * Decision 3: exactly one required field (the raw text), no modal, no
 * confirmation, no network round trip. Enter submits; Shift+Enter inserts
 * a newline; the input stays focused across consecutive captures rather
 * than blurring after submit.
 *
 * Chips below the field show what the parser recognized (Decision 5) and
 * are individually removable before commit. Removing a date/estimate chip
 * un-applies it (its raw text goes back into the title, the field is left
 * unset); removing any other chip just dismisses the suggestion — see
 * parse.ts's resolveCapture() doc comment for why those never touch the
 * title either way.
 */
export function CaptureRoute() {
  const [text, setText] = useState('')
  const [removedKeys, setRemovedKeys] = useState<ReadonlySet<string>>(new Set())
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const { data, loading } = useQuery<RecentCapture>(RECENT_CAPTURES_SQL, [], {
    tables: ['items'],
  })

  const parsed = useMemo(() => parse(text), [text])
  const chips = parsed.tokens.filter((token) => !removedKeys.has(tokenKey(token)))

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

  function removeChip(key: string): void {
    setRemovedKeys((prev) => new Set(prev).add(key))
  }

  // Clears (and keeps focus in) the field the instant Enter is pressed,
  // without waiting for the write to finish — Decision 3 says capture must
  // never block, and that includes never disabling the field while its
  // write is in flight.
  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>): void {
    if (event.key !== 'Enter' || event.shiftKey || event.nativeEvent.isComposing) return
    event.preventDefault()
    const raw = text
    const resolved = resolveCapture(raw, removedKeys)
    // A pure date/estimate capture (e.g. just "tomorrow") strips down to an
    // empty title — falling back to the raw text, unparsed, is what keeps
    // "unparsed input still produces a valid item" true even then, since
    // items.title can never be empty. scheduledFor/estimateMin still apply
    // regardless: the fallback only concerns what the title *displays*.
    const title = resolved.title.trim().length > 0 ? resolved.title : raw.trim()
    if (title.length === 0) return
    setText('')
    setRemovedKeys(new Set())
    void captureTask(
      { title, scheduledFor: resolved.scheduledFor, estimateMin: resolved.estimateMin },
      { mutate: (input) => dbClient.mutate(input) },
    )
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
          <svg
            aria-hidden="true"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <rect x="9" y="2" width="6" height="12" rx="3" />
            <path d="M5 11a7 7 0 0 0 14 0" />
            <line x1="12" y1="18" x2="12" y2="22" />
            <line x1="8" y1="22" x2="16" y2="22" />
          </svg>
        </button>
      </div>

      {chips.length > 0 ? (
        <ul className={styles.chips} aria-label="Parsed from your capture">
          {chips.map((token) => (
            <li key={`${tokenKey(token)}-${token.start.toString()}`}>
              <button
                type="button"
                className={styles.chip}
                aria-label={`Remove ${token.label}`}
                onClick={() => {
                  removeChip(tokenKey(token))
                }}
              >
                <span aria-hidden="true">{token.label}</span>
                <span aria-hidden="true" className={styles.chipRemove}>
                  ×
                </span>
              </button>
            </li>
          ))}
        </ul>
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
