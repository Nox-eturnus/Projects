import { describe, expect, it } from 'vitest'
import { parse, resolveCapture, tokenKey, type ParsedToken, type TokenType } from './parse'

// Always a real Wednesday, whatever day this suite actually runs on — the
// weekday-resolution rules ("same weekday as today resolves to today, not
// +7 days") need a known day-of-week to assert against without hardcoding
// a calendar date that could someday cause a leap-year/DST coincidence.
function nearestWednesday(from: number): number {
  const d = new Date(from)
  d.setDate(d.getDate() + ((3 - d.getDay() + 7) % 7))
  d.setHours(10, 0, 0, 0)
  return d.getTime()
}

const NOW = nearestWednesday(Date.now())

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
function atTime(dayStart: number, hour: number, minute = 0): number {
  return dayStart + (hour * 60 + minute) * 60_000
}

const TODAY = startOfDay(NOW) // Wednesday
const TOMORROW = startOfDay(addDays(NOW, 1)) // Thursday
const NEXT_MON = startOfDay(addDays(NOW, 5))
const NEXT_TUE = startOfDay(addDays(NOW, 6))
const NEXT_FRI = startOfDay(addDays(NOW, 2))
const NEXT_SAT = startOfDay(addDays(NOW, 3))
const NEXT_SUN = startOfDay(addDays(NOW, 4))

it('sanity: the computed reference "now" really is a Wednesday', () => {
  expect(new Date(NOW).getDay()).toBe(3)
})

interface ExpectedToken {
  readonly type: TokenType
  readonly [key: string]: unknown
}

function check(
  input: string,
  expectedTitle: string,
  expectedTokens: readonly ExpectedToken[],
): void {
  const result = parse(input, NOW)
  expect(result.title).toBe(expectedTitle)
  expect(result.tokens).toHaveLength(expectedTokens.length)
  result.tokens.forEach((token, i) => {
    expect(token).toMatchObject(expectedTokens[i])
  })
}

describe('dates and times', () => {
  it('today', () => {
    check('today', '', [{ type: 'date', timestamp: TODAY, hasTime: false }])
  })
  it('Today (case-insensitive)', () => {
    check('Today', '', [{ type: 'date', timestamp: TODAY, hasTime: false }])
  })
  it('tomorrow', () => {
    check('tomorrow', '', [{ type: 'date', timestamp: TOMORROW, hasTime: false }])
  })
  it('Tomorrow', () => {
    check('Tomorrow', '', [{ type: 'date', timestamp: TOMORROW, hasTime: false }])
  })

  it('mon (abbreviated)', () => {
    check('mon', '', [{ type: 'date', timestamp: NEXT_MON }])
  })
  it('monday (full)', () => {
    check('monday', '', [{ type: 'date', timestamp: NEXT_MON }])
  })
  it('tue', () => {
    check('tue', '', [{ type: 'date', timestamp: NEXT_TUE }])
  })
  it('tuesday', () => {
    check('tuesday', '', [{ type: 'date', timestamp: NEXT_TUE }])
  })
  it('wed resolves to TODAY, not +7 days', () => {
    check('wed', '', [{ type: 'date', timestamp: TODAY }])
  })
  it('wednesday resolves to TODAY', () => {
    check('wednesday', '', [{ type: 'date', timestamp: TODAY }])
  })
  it('thu', () => {
    check('thu', '', [{ type: 'date', timestamp: TOMORROW }])
  })
  it('thursday', () => {
    check('thursday', '', [{ type: 'date', timestamp: TOMORROW }])
  })
  it('fri', () => {
    check('fri', '', [{ type: 'date', timestamp: NEXT_FRI }])
  })
  it('friday', () => {
    check('friday', '', [{ type: 'date', timestamp: NEXT_FRI }])
  })
  it('sat', () => {
    check('sat', '', [{ type: 'date', timestamp: NEXT_SAT }])
  })
  it('saturday', () => {
    check('saturday', '', [{ type: 'date', timestamp: NEXT_SAT }])
  })
  it('sun', () => {
    check('sun', '', [{ type: 'date', timestamp: NEXT_SUN }])
  })
  it('sunday', () => {
    check('sunday', '', [{ type: 'date', timestamp: NEXT_SUN }])
  })

  it('next week', () => {
    check('next week', '', [
      { type: 'date', timestamp: startOfDay(addDays(NOW, 7)), label: 'Next week' },
    ])
  })
  it('NEXT WEEK (case-insensitive)', () => {
    check('NEXT WEEK', '', [{ type: 'date', timestamp: startOfDay(addDays(NOW, 7)) }])
  })
  it('in 3 days', () => {
    check('in 3 days', '', [
      { type: 'date', timestamp: startOfDay(addDays(NOW, 3)), label: 'In 3 days' },
    ])
  })
  it('in 1 day (singular)', () => {
    check('in 1 day', '', [
      { type: 'date', timestamp: startOfDay(addDays(NOW, 1)), label: 'In 1 day' },
    ])
  })
  it('in 10 days', () => {
    check('in 10 days', '', [{ type: 'date', timestamp: startOfDay(addDays(NOW, 10)) }])
  })

  it('3pm', () => {
    check('3pm', '', [{ type: 'date', timestamp: atTime(TODAY, 15, 0), hasTime: true }])
  })
  it('3:30pm', () => {
    check('3:30pm', '', [{ type: 'date', timestamp: atTime(TODAY, 15, 30) }])
  })
  it('10am', () => {
    check('10am', '', [{ type: 'date', timestamp: atTime(TODAY, 10, 0) }])
  })
  it('12am is midnight', () => {
    check('12am', '', [{ type: 'date', timestamp: atTime(TODAY, 0, 0) }])
  })
  it('12pm is noon', () => {
    check('12pm', '', [{ type: 'date', timestamp: atTime(TODAY, 12, 0) }])
  })
  it('11:59pm', () => {
    check('11:59pm', '', [{ type: 'date', timestamp: atTime(TODAY, 23, 59) }])
  })
  it('15:00 (24h)', () => {
    check('15:00', '', [{ type: 'date', timestamp: atTime(TODAY, 15, 0) }])
  })
  it('9:05 (24h, no am/pm)', () => {
    check('9:05', '', [{ type: 'date', timestamp: atTime(TODAY, 9, 5) }])
  })

  it('tomorrow 3pm (combo)', () => {
    check('tomorrow 3pm', '', [{ type: 'date', timestamp: atTime(TOMORROW, 15, 0), hasTime: true }])
  })
  it('monday 15:00 (combo)', () => {
    check('monday 15:00', '', [{ type: 'date', timestamp: atTime(NEXT_MON, 15, 0) }])
  })

  it('every monday (recurring)', () => {
    check('every monday', '', [
      { type: 'date', timestamp: NEXT_MON, recurring: true, label: 'Every Monday' },
    ])
  })
  it('every fri (recurring, abbreviated)', () => {
    check('every fri', '', [
      { type: 'date', timestamp: NEXT_FRI, recurring: true, label: 'Every Friday' },
    ])
  })

  it('21/8 (unambiguous: no month 21 exists, so day-first)', () => {
    const expected = new Date(new Date(NOW).getFullYear(), 7, 21)
    if (expected.getTime() < TODAY) expected.setFullYear(expected.getFullYear() + 1)
    check('21/8', '', [{ type: 'date', timestamp: expected.getTime(), hasTime: false }])
  })
  it('5/6 — the documented ambiguous case: day-first, so June 5th, not May 6th', () => {
    const expected = new Date(new Date(NOW).getFullYear(), 5, 5)
    if (expected.getTime() < TODAY) expected.setFullYear(expected.getFullYear() + 1)
    check('5/6', '', [{ type: 'date', timestamp: expected.getTime() }])
  })
  it('1/1 rolls to next year if 1 Jan already passed this year', () => {
    const expected = new Date(new Date(NOW).getFullYear(), 0, 1)
    if (expected.getTime() < TODAY) expected.setFullYear(expected.getFullYear() + 1)
    check('1/1', '', [{ type: 'date', timestamp: expected.getTime() }])
  })
  it('31/12', () => {
    const expected = new Date(new Date(NOW).getFullYear(), 11, 31)
    if (expected.getTime() < TODAY) expected.setFullYear(expected.getFullYear() + 1)
    check('31/12', '', [{ type: 'date', timestamp: expected.getTime() }])
  })
  it('40/13 is out of range — not a date, left as plain text', () => {
    check('40/13', '40/13', [])
  })
})

describe('@person and #project', () => {
  it('@Rahul', () => {
    check('@Rahul', '', [{ type: 'person', name: 'Rahul', label: '@Rahul' }])
  })
  it('@sarah-jones (hyphenated name)', () => {
    check('@sarah-jones', '', [{ type: 'person', name: 'sarah-jones' }])
  })
  it('#groceries', () => {
    check('#groceries', '', [{ type: 'project', name: 'groceries', label: '#groceries' }])
  })
  it('#Project1', () => {
    check('#Project1', '', [{ type: 'project', name: 'Project1' }])
  })
  it('@Rahul #groceries together', () => {
    check('@Rahul #groceries', '', [
      { type: 'person', name: 'Rahul' },
      { type: 'project', name: 'groceries' },
    ])
  })
})

describe('priority', () => {
  it('!', () => {
    check('!', '', [{ type: 'priority', level: 1 }])
  })
  it('!!', () => {
    check('!!', '', [{ type: 'priority', level: 2 }])
  })
  it('!!!', () => {
    check('!!!', '', [{ type: 'priority', level: 3 }])
  })
  it('!!!! (4 marks) is ambiguous — matches nothing, stays plain text', () => {
    check('!!!!', '!!!!', [])
  })
  it('task !! urgent (embedded)', () => {
    check('task !! urgent', 'task urgent', [{ type: 'priority', level: 2 }])
  })
})

describe('routine (*) and question (?) prefixes', () => {
  it('*Gym — leading * is a routine marker', () => {
    check('*Gym', 'Gym', [{ type: 'routine', raw: '*' }])
  })
  it('Gym * — trailing * is not a routine marker, stays literal', () => {
    check('Gym *', 'Gym *', [])
  })
  it('?Should I buy this — leading ? files as a question', () => {
    check('?Should I buy this', 'Should I buy this', [{ type: 'question', raw: '?' }])
  })
  it('Did I already buy milk? — trailing ? is just punctuation', () => {
    check('Did I already buy milk?', 'Did I already buy milk?', [])
  })
  it('  *Gym — leading whitespace before * still counts as leading', () => {
    check('  *Gym', 'Gym', [{ type: 'routine' }])
  })
})

describe('estimate', () => {
  it('~45m', () => {
    check('~45m', '', [{ type: 'estimate', minutes: 45 }])
  })
  it('~2h', () => {
    check('~2h', '', [{ type: 'estimate', minutes: 120 }])
  })
  it('~90M (case-insensitive unit)', () => {
    check('~90M', '', [{ type: 'estimate', minutes: 90 }])
  })
})

describe('combined and unparsed input', () => {
  it('Buy milk @Rahul #groceries !! tomorrow 3pm ~30m', () => {
    check('Buy milk @Rahul #groceries !! tomorrow 3pm ~30m', 'Buy milk', [
      { type: 'person', name: 'Rahul' },
      { type: 'project', name: 'groceries' },
      { type: 'priority', level: 2 },
      { type: 'date', timestamp: atTime(TOMORROW, 15, 0) },
      { type: 'estimate', minutes: 30 },
    ])
  })
  it('*Every monday gym session ~1h', () => {
    check('*Every monday gym session ~1h', 'gym session', [
      { type: 'routine' },
      { type: 'date', timestamp: NEXT_MON, recurring: true },
      { type: 'estimate', minutes: 60 },
    ])
  })
  it('TODAY !!! @Bob #work ~15m (all-caps date keyword)', () => {
    check('TODAY !!! @Bob #work ~15m', '', [
      { type: 'date', timestamp: TODAY },
      { type: 'priority', level: 3 },
      { type: 'person', name: 'Bob' },
      { type: 'project', name: 'work' },
      { type: 'estimate', minutes: 15 },
    ])
  })

  it('plain text with no tokens', () => {
    check('Buy milk', 'Buy milk', [])
  })
  it('surrounding whitespace is trimmed', () => {
    check('  Buy milk  ', 'Buy milk', [])
  })
  it('empty string', () => {
    check('', '', [])
  })
  it('whitespace only', () => {
    check('   ', '', [])
  })
})

describe('parse() is pure', () => {
  it('the same input and now always produce the same result', () => {
    const a = parse('Buy milk @Rahul tomorrow 3pm ~30m', NOW)
    const b = parse('Buy milk @Rahul tomorrow 3pm ~30m', NOW)
    expect(a).toEqual(b)
  })

  it('has no dependency on ambient time — an explicit now is required for determinism', () => {
    const a = parse('today', 1_700_000_000_000)
    const b = parse('today', 1_700_000_000_000)
    expect(a).toEqual(b)
  })
})

describe('resolveCapture', () => {
  it('with no rejections, applies every date/estimate token and strips them from the title', () => {
    const result = resolveCapture('Buy milk tomorrow 3pm ~30m @Rahul', new Set(), NOW)
    expect(result.title).toBe('Buy milk @Rahul')
    expect(result.scheduledFor).toBe(atTime(TOMORROW, 15, 0))
    expect(result.estimateMin).toBe(30)
  })

  it('a rejected date token leaves its raw text in the title and scheduledFor null', () => {
    const tokens = parse('Buy milk tomorrow', NOW).tokens
    const dateToken = tokens.find(
      (t): t is Extract<ParsedToken, { type: 'date' }> => t.type === 'date',
    )
    if (!dateToken) throw new Error('expected a date token')
    const rejected = new Set([tokenKey(dateToken)])
    const result = resolveCapture('Buy milk tomorrow', rejected, NOW)
    expect(result.title).toBe('Buy milk tomorrow')
    expect(result.scheduledFor).toBeNull()
  })

  it('a rejected estimate token leaves its raw text in the title and estimateMin null', () => {
    const tokens = parse('Buy milk ~45m', NOW).tokens
    const estimateToken = tokens.find(
      (t): t is Extract<ParsedToken, { type: 'estimate' }> => t.type === 'estimate',
    )
    if (!estimateToken) throw new Error('expected an estimate token')
    const rejected = new Set([tokenKey(estimateToken)])
    const result = resolveCapture('Buy milk ~45m', rejected, NOW)
    expect(result.title).toBe('Buy milk ~45m')
    expect(result.estimateMin).toBeNull()
  })

  it('multiple date tokens: the last one wins for scheduledFor', () => {
    const result = resolveCapture('today or tomorrow', new Set(), NOW)
    expect(result.scheduledFor).toBe(TOMORROW)
  })

  it('person/project/priority/routine/question tokens are never stripped, accepted or not', () => {
    const input = '*?!@Bob'
    // Only the leading char can be a routine/question prefix, and it's
    // already '*' here, so '?' is never extracted as a token at all — it's
    // just punctuation. The other three (routine, priority, person) are
    // real tokens with nowhere to write yet, so unlike a date/estimate
    // token, whether they're "rejected" makes no difference to the title.
    const tokens = parse(input, NOW).tokens
    expect(tokens.map((t) => t.type)).toEqual(['routine', 'priority', 'person'])

    const noneRejected = resolveCapture(input, new Set(), NOW)
    const allRejected = resolveCapture(input, new Set(tokens.map(tokenKey)), NOW)
    expect(noneRejected.title).toBe(input.trim())
    expect(allRejected.title).toBe(input.trim())
  })

  it('blank input resolves to an empty title with no fields set', () => {
    const result = resolveCapture('   ', new Set(), NOW)
    expect(result).toEqual({ title: '', scheduledFor: null, estimateMin: null })
  })
})
