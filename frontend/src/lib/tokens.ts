/**
 * Design tokens for chart code. Recharts draws SVG and needs colour values rather than
 * Tailwind classes, so the chart colours are repeated here from src/styles/global.css
 * (docs/design.md §2). tokens.test.ts fails if the two ever differ.
 */
export const COLORS = {
  ink: '#18212b',
  graphite: '#4a5562',
  slate: '#67717c',
  paper: '#ffffff',
  rule: '#d5d9dd',
  signal: '#1f5f99',
  copper: '#c2581f',
} as const

export const CHART_FONT_SIZE = 12
