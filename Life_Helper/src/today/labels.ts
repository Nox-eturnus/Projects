/**
 * The short text under a task on Today and in the shutdown: when it's
 * scheduled, when it's due, why it was proposed. Formatted by hand, the
 * same way parse.ts formats its chips, so it reads identically on every
 * device regardless of the browser's locale.
 *
 * Decision 7 applies to every string here: a task scheduled for an
 * earlier day is "carried over" or "from Tue 8 Sep," never "overdue," and
 * nothing is ever counted up or coloured as a failure.
 */
import { compareLocalDays, startOfLocalDay } from '../scheduling/localDay.js'
import type { Candidate, DayTask } from './proposal.js'

const WEEKDAY_SHORT = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
const WEEKDAY_LONG = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
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
const MONTH_LONG = [
  'January',
  'February',
  'March',
  'April',
  'May',
  'June',
  'July',
  'August',
  'September',
  'October',
  'November',
  'December',
]

/** "Friday 11 September" — a page's date heading. */
export function formatLongDate(ms: number): string {
  const d = new Date(ms)
  return `${WEEKDAY_LONG[d.getDay()]} ${d.getDate().toString()} ${MONTH_LONG[d.getMonth()]}`
}

/** "Tue 8 Sep". */
export function formatShortDate(ms: number): string {
  const d = new Date(ms)
  return `${WEEKDAY_SHORT[d.getDay()]} ${d.getDate().toString()} ${MONTH_SHORT[d.getMonth()]}`
}

/** "6:00 PM" — or null for local midnight, which means "a date with no time." */
export function formatTime(ms: number): string | null {
  if (ms === startOfLocalDay(ms)) return null
  const d = new Date(ms)
  const period = d.getHours() >= 12 ? 'PM' : 'AM'
  const hour = d.getHours() % 12 === 0 ? 12 : d.getHours() % 12
  return `${hour.toString()}:${d.getMinutes().toString().padStart(2, '0')} ${period}`
}

function dayWord(ms: number, dayStart: number): string {
  const diff = compareLocalDays(ms, dayStart)
  if (diff === 0) return 'today'
  return formatShortDate(ms)
}

/**
 * The detail line for a task shown on the day starting at `dayStart`: its
 * time if it has one that day, where it came from if it was scheduled for
 * another day, and its deadline if it has one. Empty when there's nothing
 * worth saying.
 */
export function describeTask(task: DayTask, dayStart: number): string {
  const parts: string[] = []
  if (task.scheduled_for !== null) {
    const time = formatTime(task.scheduled_for)
    const sameDay = compareLocalDays(task.scheduled_for, dayStart) === 0
    if (sameDay && time) parts.push(time)
    else if (compareLocalDays(task.scheduled_for, dayStart) < 0) {
      parts.push(`From ${formatShortDate(task.scheduled_for)}`)
    }
  }
  if (task.due_at !== null) parts.push(`Due ${dayWord(task.due_at, dayStart)}`)
  return parts.join(' · ')
}

/** Why a proposed task was proposed, in plain words. */
export function describeCandidate(candidate: Candidate, dayStart: number): string {
  const { task, reason } = candidate
  const time =
    task.scheduled_for !== null && compareLocalDays(task.scheduled_for, dayStart) === 0
      ? formatTime(task.scheduled_for)
      : null
  switch (reason) {
    case 'due':
      return task.due_at === null ? 'Due' : `Due ${dayWord(task.due_at, dayStart)}`
    case 'carriedOver':
      return 'Carried over'
    case 'scheduled':
      return time ? `Scheduled, ${time}` : 'Scheduled'
  }
}

/** "these three" / "these two" / "this one" — for buttons that act on a small set. */
export function theseN(count: number): string {
  if (count === 1) return 'this one'
  if (count === 2) return 'these two'
  return 'these three'
}
