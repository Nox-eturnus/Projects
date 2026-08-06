import { describe, expect, it } from 'vitest'
import { AA_TEXT_MINIMUM, contrastPairs, contrastRatio } from './contrast'

describe('contrastRatio', () => {
  it('is 21 for black on white', () => {
    expect(contrastRatio('#000000', '#ffffff')).toBeCloseTo(21, 1)
  })

  it('is 1 for identical colors', () => {
    expect(contrastRatio('#505e53', '#505e53')).toBeCloseTo(1, 5)
  })

  it('is symmetric', () => {
    expect(contrastRatio('#505e53', '#fcf7f0')).toBeCloseTo(contrastRatio('#fcf7f0', '#505e53'), 10)
  })
})

describe('token contrast pairs', () => {
  const textPairs = contrastPairs.filter((pair) => pair.requiredForText)

  it('covers ink and ink-secondary against both surfaces, in both themes', () => {
    expect(textPairs).toHaveLength(8)
  })

  it.each(textPairs)('$label ($theme) passes WCAG AA for normal text', (pair) => {
    expect(pair.ratio).toBeGreaterThanOrEqual(AA_TEXT_MINIMUM)
  })
})
