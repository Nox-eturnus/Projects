import { describe, expect, it } from 'vitest'
import { generateItemId } from './id'

const UUID_SHAPE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/

describe('generateItemId', () => {
  it('produces a well-formed UUID string', () => {
    expect(generateItemId()).toMatch(UUID_SHAPE)
  })

  it('sets the version nibble to 7', () => {
    const id = generateItemId()
    expect(id[14]).toBe('7')
  })

  it('sets the variant bits to 10xx (the RFC 4122/9562 variant)', () => {
    const id = generateItemId()
    const variantNibble = Number.parseInt(id[19], 16)
    expect(variantNibble & 0b1100).toBe(0b1000)
  })

  it('never collides across a burst of calls', () => {
    const ids = new Set(Array.from({ length: 1000 }, () => generateItemId()))
    expect(ids.size).toBe(1000)
  })

  it('sorts lexicographically by the timestamp it was generated with', () => {
    const earlier = generateItemId(1_700_000_000_000)
    const later = generateItemId(1_700_000_000_001)
    expect(earlier < later).toBe(true)
  })

  it('encodes the millisecond timestamp in the leading 48 bits, round-trippable', () => {
    const now = 1_700_000_123_456
    const id = generateItemId(now)
    const hex = id.replace(/-/g, '').slice(0, 12)
    expect(Number.parseInt(hex, 16)).toBe(now)
  })
})
