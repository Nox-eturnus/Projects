/**
 * WCAG 2.1 contrast math, plus the token values themselves, as a single source of
 * truth shared by the contrast regression test, the gallery route, and
 * docs/phase_A4_design_system.md's ratio table.
 *
 * Keep these hex values byte-identical to the custom properties in `tokens.css` —
 * CSS can't import from here, so the two are kept in sync by hand (same rule
 * Decision 13 already applies to the icon and this token file).
 */

export interface ColorTokens {
  surfacePaper: string
  surfaceRaised: string
  ink: string
  inkSecondary: string
  mutedFill: string
  accentFill: string
  hairline: string
}

// Source values sampled from the app icon (Decision 13).
export const lightTokens: ColorTokens = {
  surfacePaper: '#fcf7f0',
  surfaceRaised: '#f4ebe0',
  ink: '#505e53',
  inkSecondary: '#616d60',
  mutedFill: '#9d937f',
  accentFill: '#d1b594',
  hairline: '#e3dcd0',
}

// Derived from the icon's deep green as the base surface with cream as ink,
// re-measured rather than a colour inversion of the light tokens.
export const darkTokens: ColorTokens = {
  surfacePaper: '#20261f',
  surfaceRaised: '#2a3128',
  ink: '#f4ebe0',
  inkSecondary: '#c9c0ab',
  mutedFill: '#8b8270',
  accentFill: '#a9835c',
  hairline: '#3a4238',
}

function srgbToLinear(channel: number): number {
  const c = channel / 255
  return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4)
}

function relativeLuminance(hex: string): number {
  const normalized = hex.replace('#', '')
  const r = parseInt(normalized.slice(0, 2), 16)
  const g = parseInt(normalized.slice(2, 4), 16)
  const b = parseInt(normalized.slice(4, 6), 16)
  return 0.2126 * srgbToLinear(r) + 0.7152 * srgbToLinear(g) + 0.0722 * srgbToLinear(b)
}

/** WCAG contrast ratio of two sRGB hex colors, in the range [1, 21]. */
export function contrastRatio(hexA: string, hexB: string): number {
  const lumA = relativeLuminance(hexA)
  const lumB = relativeLuminance(hexB)
  const lighter = Math.max(lumA, lumB)
  const darker = Math.min(lumA, lumB)
  return (lighter + 0.05) / (darker + 0.05)
}

/** WCAG AA minimum for normal-size text. */
export const AA_TEXT_MINIMUM = 4.5

export type Theme = 'light' | 'dark'

export interface ContrastPair {
  label: string
  theme: Theme
  foreground: keyof ColorTokens
  background: keyof ColorTokens
  ratio: number
  /** Only `ink` and `inkSecondary` are cleared to carry text (Decision 13). */
  requiredForText: boolean
}

const TEXT_FOREGROUNDS = ['ink', 'inkSecondary'] as const
const TEXT_BACKGROUNDS = ['surfacePaper', 'surfaceRaised'] as const
const DECORATIVE_FOREGROUNDS = ['mutedFill', 'accentFill'] as const

function buildPairsForTheme(theme: Theme, tokens: ColorTokens): ContrastPair[] {
  const pairs: ContrastPair[] = []
  for (const fg of TEXT_FOREGROUNDS) {
    for (const bg of TEXT_BACKGROUNDS) {
      pairs.push({
        label: `${fg} on ${bg}`,
        theme,
        foreground: fg,
        background: bg,
        ratio: contrastRatio(tokens[fg], tokens[bg]),
        requiredForText: true,
      })
    }
  }
  for (const fg of DECORATIVE_FOREGROUNDS) {
    pairs.push({
      label: `${fg} on surfacePaper (decorative only, never text)`,
      theme,
      foreground: fg,
      background: 'surfacePaper',
      ratio: contrastRatio(tokens[fg], tokens.surfacePaper),
      requiredForText: false,
    })
  }
  return pairs
}

/** Every token pair worth recording, computed from the hex values above. */
export const contrastPairs: ContrastPair[] = [
  ...buildPairsForTheme('light', lightTokens),
  ...buildPairsForTheme('dark', darkTokens),
]
