/**
 * Part B2's deterministic capture parser (Decision 5): pure, synchronous,
 * dependency-free. Recognizes dates/times, @person, #project, !/!!/!!!
 * priority, a leading `*` (routine) or `?` (question), and `~45m`/`~2h`
 * estimates. Unmatched text remains the title.
 *
 * `parse()` finds every recognizable token. `resolveCapture()` is what
 * CaptureRoute actually calls on submit: it takes the set of chips the
 * user has *not* rejected and turns them into the title text plus the two
 * fields that already have a home in the schema (`scheduled_for`,
 * `estimate_min`) — see docs/phase_B2_deterministic_parser.md for why
 * @person/#project/priority/routine/question are parsed and shown as
 * chips but not yet written anywhere beyond that.
 */

export type TokenType =
  'date' | 'person' | 'project' | 'priority' | 'routine' | 'question' | 'estimate'

interface BaseToken {
  readonly raw: string
  readonly start: number
  readonly end: number
  readonly label: string
}

export type ParsedToken =
  | (BaseToken & { type: 'date'; timestamp: number; hasTime: boolean; recurring: boolean })
  | (BaseToken & { type: 'person'; name: string })
  | (BaseToken & { type: 'project'; name: string })
  | (BaseToken & { type: 'priority'; level: 1 | 2 | 3 })
  | (BaseToken & { type: 'routine' })
  | (BaseToken & { type: 'question' })
  | (BaseToken & { type: 'estimate'; minutes: number })

export interface ParseResult {
  readonly title: string
  readonly tokens: readonly ParsedToken[]
}

export interface ResolvedCapture {
  readonly title: string
  readonly scheduledFor: number | null
  readonly estimateMin: number | null
}

const WEEKDAY_INDEX: Record<string, number> = {
  sun: 0,
  sunday: 0,
  mon: 1,
  monday: 1,
  tue: 2,
  tuesday: 2,
  wed: 3,
  wednesday: 3,
  thu: 4,
  thursday: 4,
  fri: 5,
  friday: 5,
  sat: 6,
  saturday: 6,
}

const WEEKDAY_FULL: Record<string, string> = {
  sun: 'sunday',
  mon: 'monday',
  tue: 'tuesday',
  wed: 'wednesday',
  thu: 'thursday',
  fri: 'friday',
  sat: 'saturday',
}

const WEEKDAY_SHORT = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
const MONTH_SHORT = [
  'Jan',
  'Feb',
  'Mar',
  'Apr',
  'May',
  'Jun',
  'Jul',
  'Aug',
  'Sep',
  'Oct',
  'Nov',
  'Dec',
]

const WEEKDAY_PATTERN =
  '(?:mon(?:day)?|tue(?:sday)?|wed(?:nesday)?|thu(?:rsday)?|fri(?:day)?|sat(?:urday)?|sun(?:day)?)'
const TIME_PATTERN = '(?:\\d{1,2}:\\d{2}(?:\\s*(?:am|pm))?|\\d{1,2}\\s*(?:am|pm))'
const DATEWORD_PATTERN = `(?:today|tomorrow|${WEEKDAY_PATTERN})`
const NUMERIC_DATE_PATTERN = '\\d{1,2}/\\d{1,2}'

// Alternatives are ordered most-specific/longest first — a single global
// regex.exec pass tries alternatives left-to-right at each position, so
// "tomorrow 3pm" must offer the combo alternative before the bare
// "tomorrow" one or the combo would never win.
const DATE_REGEX = new RegExp(
  '\\b(?:' +
    [
      `(?<everyDay>every\\s+${WEEKDAY_PATTERN})`,
      `(?<nextWeek>next\\s+week)`,
      `(?<inDays>in\\s+\\d+\\s+days?)`,
      `(?<dateWordTime>${DATEWORD_PATTERN}\\s+${TIME_PATTERN})`,
      `(?<numDateTime>${NUMERIC_DATE_PATTERN}\\s+${TIME_PATTERN})`,
      `(?<numDate>${NUMERIC_DATE_PATTERN})`,
      `(?<dateWord>${DATEWORD_PATTERN})`,
      `(?<timeOnly>${TIME_PATTERN})`,
    ].join('|') +
    ')\\b',
  'gi',
)

const MENTION_REGEX = /([@#])([A-Za-z0-9][\w-]*)/g

// A run of 4+ "!" matches neither this nor a shorter run within it (the
// lookahead/lookbehind reject every possible 1-3 length window inside a
// longer run) — the documented, tested resolution for that ambiguous case.
const PRIORITY_REGEX = /(?<!!)!{1,3}(?!!)/g

const ESTIMATE_REGEX = /~(\d+)(m|h)\b/gi

function startOfDay(ms: number): number {
  const d = new Date(ms)
  d.setHours(0, 0, 0, 0)
  return d.getTime()
}

function addDays(ms: number, days: number): number {
  const d = new Date(ms)
  d.setDate(d.getDate() + days)
  return d.getTime()
}

function capitalize(word: string): string {
  return word.charAt(0).toUpperCase() + word.slice(1)
}

/** Same weekday as `now` resolves to today (0 days ahead), not 7. */
function resolveWeekday(word: string, now: number): number {
  const idx = WEEKDAY_INDEX[word.toLowerCase()]
  const current = new Date(now).getDay()
  const diff = (idx - current + 7) % 7
  return startOfDay(addDays(now, diff))
}

function resolveDateWord(word: string, now: number): number {
  const lower = word.toLowerCase()
  if (lower === 'today') return startOfDay(now)
  if (lower === 'tomorrow') return startOfDay(addDays(now, 1))
  return resolveWeekday(lower, now)
}

function parseTimeOfDay(text: string, dayStart: number): number {
  const trimmed = text.trim().toLowerCase()
  const ampm = /^(\d{1,2})(?::(\d{2}))?\s*(am|pm)$/.exec(trimmed)
  if (ampm) {
    let hour = Number(ampm[1])
    const minute = ampm[2] ? Number(ampm[2]) : 0
    if (ampm[3] === 'am') {
      if (hour === 12) hour = 0
    } else if (hour !== 12) {
      hour += 12
    }
    return dayStart + (hour * 60 + minute) * 60_000
  }
  const h24 = /^(\d{1,2}):(\d{2})$/.exec(trimmed)
  if (h24) {
    return dayStart + (Number(h24[1]) * 60 + Number(h24[2])) * 60_000
  }
  throw new Error(`parseTimeOfDay: unrecognized time "${text}"`)
}

/**
 * `DD/MM`, day first — the only rule that makes `21/8` (unambiguous: no
 * month 21 exists) and the genuinely ambiguous `5/6` both resolve the same
 * way. Rolls to next year if the resulting date has already passed this
 * year. Returns null (leaving the digits as plain text) for an
 * out-of-range day/month, e.g. `40/13`.
 */
function resolveNumericDate(text: string, now: number): number | null {
  const m = /^(\d{1,2})\/(\d{1,2})$/.exec(text)
  if (!m) return null
  const day = Number(m[1])
  const month = Number(m[2])
  if (day < 1 || day > 31 || month < 1 || month > 12) return null
  const nowDate = new Date(now)
  let year = nowDate.getFullYear()
  let candidate = new Date(year, month - 1, day)
  if (candidate.getTime() < startOfDay(now)) {
    year += 1
    candidate = new Date(year, month - 1, day)
  }
  return candidate.getTime()
}

function formatDateLabel(timestamp: number, hasTime: boolean, now: number): string {
  const day = startOfDay(timestamp)
  const today = startOfDay(now)
  const tomorrow = startOfDay(addDays(now, 1))
  let datePart: string
  if (day === today) datePart = 'Today'
  else if (day === tomorrow) datePart = 'Tomorrow'
  else {
    const d = new Date(timestamp)
    datePart = `${WEEKDAY_SHORT[d.getDay()]} ${d.getDate().toString()} ${MONTH_SHORT[d.getMonth()]}`
  }
  if (!hasTime) return datePart
  const d = new Date(timestamp)
  let hour = d.getHours()
  const minute = d.getMinutes()
  const period = hour >= 12 ? 'PM' : 'AM'
  hour = hour % 12
  if (hour === 0) hour = 12
  return `${datePart}, ${hour.toString()}:${minute.toString().padStart(2, '0')} ${period}`
}

interface DateValue {
  readonly timestamp: number
  readonly hasTime: boolean
  readonly recurring: boolean
  readonly label: string
}

function splitOnFirstSpace(text: string): readonly [string, string] {
  const spaceIdx = text.search(/\s/)
  return [text.slice(0, spaceIdx), text.slice(spaceIdx).trim()]
}

function computeDateValue(
  groups: Record<string, string | undefined>,
  now: number,
): DateValue | null {
  if (groups.everyDay) {
    const weekdayWord = groups.everyDay.replace(/^every\s+/i, '')
    const timestamp = resolveWeekday(weekdayWord, now)
    const full = WEEKDAY_FULL[weekdayWord.toLowerCase()] ?? weekdayWord.toLowerCase()
    return { timestamp, hasTime: false, recurring: true, label: `Every ${capitalize(full)}` }
  }
  if (groups.nextWeek) {
    return {
      timestamp: startOfDay(addDays(now, 7)),
      hasTime: false,
      recurring: false,
      label: 'Next week',
    }
  }
  if (groups.inDays) {
    const n = Number(/\d+/.exec(groups.inDays)?.[0] ?? '0')
    return {
      timestamp: startOfDay(addDays(now, n)),
      hasTime: false,
      recurring: false,
      label: `In ${n.toString()} day${n === 1 ? '' : 's'}`,
    }
  }
  if (groups.dateWordTime) {
    const [dateWordPart, timePart] = splitOnFirstSpace(groups.dateWordTime)
    const dayStart = resolveDateWord(dateWordPart, now)
    const timestamp = parseTimeOfDay(timePart, dayStart)
    return {
      timestamp,
      hasTime: true,
      recurring: false,
      label: formatDateLabel(timestamp, true, now),
    }
  }
  if (groups.numDateTime) {
    const [numPart, timePart] = splitOnFirstSpace(groups.numDateTime)
    const dayStart = resolveNumericDate(numPart, now)
    if (dayStart === null) return null
    const timestamp = parseTimeOfDay(timePart, dayStart)
    return {
      timestamp,
      hasTime: true,
      recurring: false,
      label: formatDateLabel(timestamp, true, now),
    }
  }
  if (groups.numDate) {
    const timestamp = resolveNumericDate(groups.numDate, now)
    if (timestamp === null) return null
    return {
      timestamp,
      hasTime: false,
      recurring: false,
      label: formatDateLabel(timestamp, false, now),
    }
  }
  if (groups.dateWord) {
    const timestamp = resolveDateWord(groups.dateWord, now)
    return {
      timestamp,
      hasTime: false,
      recurring: false,
      label: formatDateLabel(timestamp, false, now),
    }
  }
  if (groups.timeOnly) {
    const timestamp = parseTimeOfDay(groups.timeOnly, startOfDay(now))
    return {
      timestamp,
      hasTime: true,
      recurring: false,
      label: formatDateLabel(timestamp, true, now),
    }
  }
  return null
}

function extractDateTokens(input: string, now: number): ParsedToken[] {
  const tokens: ParsedToken[] = []
  for (const match of input.matchAll(DATE_REGEX)) {
    const resolved = computeDateValue(match.groups ?? {}, now)
    if (!resolved) continue
    const raw = match[0]
    const start = match.index
    tokens.push({
      type: 'date',
      raw,
      start,
      end: start + raw.length,
      timestamp: resolved.timestamp,
      hasTime: resolved.hasTime,
      recurring: resolved.recurring,
      label: resolved.label,
    })
  }
  return tokens
}

function extractMentionTokens(input: string): ParsedToken[] {
  const tokens: ParsedToken[] = []
  for (const match of input.matchAll(MENTION_REGEX)) {
    const raw = match[0]
    const start = match.index
    const name = match[2]
    if (match[1] === '@') {
      tokens.push({ type: 'person', raw, start, end: start + raw.length, name, label: raw })
    } else {
      tokens.push({ type: 'project', raw, start, end: start + raw.length, name, label: raw })
    }
  }
  return tokens
}

function extractPriorityTokens(input: string): ParsedToken[] {
  const tokens: ParsedToken[] = []
  for (const match of input.matchAll(PRIORITY_REGEX)) {
    const raw = match[0]
    const start = match.index
    tokens.push({
      type: 'priority',
      raw,
      start,
      end: start + raw.length,
      level: raw.length as 1 | 2 | 3,
      label: raw,
    })
  }
  return tokens
}

/** `*`/`?` only count as the routine/question marker when they lead the
 * (trimmed) input — mid-text they're just punctuation. */
function extractPrefixTokens(input: string): ParsedToken[] {
  const leadingWhitespace = input.length - input.trimStart().length
  const firstChar = input[leadingWhitespace]
  if (firstChar === '*') {
    return [
      {
        type: 'routine',
        raw: '*',
        start: leadingWhitespace,
        end: leadingWhitespace + 1,
        label: '*',
      },
    ]
  }
  if (firstChar === '?') {
    return [
      {
        type: 'question',
        raw: '?',
        start: leadingWhitespace,
        end: leadingWhitespace + 1,
        label: '?',
      },
    ]
  }
  return []
}

function extractEstimateTokens(input: string): ParsedToken[] {
  const tokens: ParsedToken[] = []
  for (const match of input.matchAll(ESTIMATE_REGEX)) {
    const raw = match[0]
    const start = match.index
    const amount = Number(match[1])
    const minutes = match[2].toLowerCase() === 'h' ? amount * 60 : amount
    tokens.push({ type: 'estimate', raw, start, end: start + raw.length, minutes, label: raw })
  }
  return tokens
}

const CATEGORY_PRIORITY: Record<TokenType, number> = {
  date: 0,
  person: 1,
  project: 2,
  priority: 3,
  routine: 4,
  question: 5,
  estimate: 6,
}

/** Greedy, non-overlapping accept: longest match wins at a given start
 * position, category listing order (dates first, per the plan) breaks
 * remaining ties. Cross-category collisions can't actually happen here
 * (every category uses a distinct trigger character/keyword) — this is
 * defensive, not load-bearing. */
function extractTokens(input: string, now: number): ParsedToken[] {
  const candidates = [
    ...extractDateTokens(input, now),
    ...extractMentionTokens(input),
    ...extractPriorityTokens(input),
    ...extractPrefixTokens(input),
    ...extractEstimateTokens(input),
  ]
  candidates.sort((a, b) => {
    if (a.start !== b.start) return a.start - b.start
    const lengthDiff = b.end - b.start - (a.end - a.start)
    if (lengthDiff !== 0) return lengthDiff
    return CATEGORY_PRIORITY[a.type] - CATEGORY_PRIORITY[b.type]
  })

  const accepted: ParsedToken[] = []
  let lastEnd = -1
  for (const candidate of candidates) {
    if (candidate.start >= lastEnd) {
      accepted.push(candidate)
      lastEnd = candidate.end
    }
  }
  return accepted
}

function stripTokens(input: string, tokens: readonly { start: number; end: number }[]): string {
  const sorted = [...tokens].sort((a, b) => a.start - b.start)
  let result = ''
  let cursor = 0
  for (const token of sorted) {
    result += input.slice(cursor, token.start)
    cursor = token.end
  }
  result += input.slice(cursor)
  return result.replace(/\s+/g, ' ').trim()
}

export function parse(input: string, now: number = Date.now()): ParseResult {
  const tokens = extractTokens(input, now)
  return { title: stripTokens(input, tokens), tokens }
}

/** Identifies a token across re-parses of edited text, so the UI can
 * remember which chips the user rejected. Duplicate identical tokens (rare
 * in capture-length text) share a key — a documented simplification, not a
 * bug: rejecting one rejects all matching instances. */
export function tokenKey(token: ParsedToken): string {
  return `${token.type}:${token.raw}`
}

/**
 * What CaptureRoute calls on submit: re-parses `input` and applies every
 * date/estimate token the user hasn't rejected (by `tokenKey`) — those are
 * the only two token types with a field to land in (`scheduled_for`,
 * `estimate_min`), so they're the only ones ever stripped from `title`;
 * rejecting one leaves its raw text in place and nulls the field.
 *
 * @person/#project/priority/routine/question tokens are never stripped
 * from `title`, accepted or not — see the module doc comment for why they
 * don't have a field to land in yet. Their chip is dismissible in the UI
 * (so the user isn't stuck staring at a suggestion the app can't act on
 * anyway), but that's a display-only gesture: nothing about `title` or the
 * write ever depends on whether one of those chips is still showing.
 * Leaving that text in place, always, is what keeps this from silently
 * discarding information B2 has nowhere to put yet.
 */
export function resolveCapture(
  input: string,
  removedKeys: ReadonlySet<string> = new Set(),
  now: number = Date.now(),
): ResolvedCapture {
  const { tokens } = parse(input, now)
  const active = tokens.filter((token) => !removedKeys.has(tokenKey(token)))
  const dateTokens = active.filter(
    (token): token is Extract<ParsedToken, { type: 'date' }> => token.type === 'date',
  )
  const estimateTokens = active.filter(
    (token): token is Extract<ParsedToken, { type: 'estimate' }> => token.type === 'estimate',
  )
  const strippable = active.filter(
    (token): token is Extract<ParsedToken, { type: 'date' | 'estimate' }> =>
      token.type === 'date' || token.type === 'estimate',
  )
  return {
    title: stripTokens(input, strippable),
    scheduledFor: dateTokens.length > 0 ? dateTokens[dateTokens.length - 1].timestamp : null,
    estimateMin:
      estimateTokens.length > 0 ? estimateTokens[estimateTokens.length - 1].minutes : null,
  }
}
