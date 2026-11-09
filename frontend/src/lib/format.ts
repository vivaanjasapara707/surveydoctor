const whole = new Intl.NumberFormat('en-GB', { maximumFractionDigits: 0 })

/** 2800 -> "2,800". */
export function formatCount(value: number): string {
  return whole.format(value)
}

/** "1 respondent" / "2 respondents". */
export function plural(count: number, singular: string, pluralForm = `${singular}s`): string {
  return `${formatCount(count)} ${count === 1 ? singular : pluralForm}`
}

const upToOneDecimal = new Intl.NumberFormat('en-GB', { maximumFractionDigits: 1 })

/** A large statistic such as Mann–Whitney U: thousands separators, at most one decimal
 *  ("519,211.5"); missing values as "—". */
export function formatLarge(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  return upToOneDecimal.format(value)
}

/** A statistic with a fixed number of decimals; missing values (JSON null) as "—". */
export function formatNumber(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  const text = value.toFixed(digits)
  // -0.00 reads as a different number from 0.00; show it as 0.00.
  return /^-0\.?0*$/.test(text) ? text.slice(1) : text
}

/** A p-value: "< 0.001" below 0.001, otherwise three decimals. */
export function formatP(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  return value < 0.001 ? '< 0.001' : value.toFixed(3)
}

/** "p < 0.001" or "p = 0.034". */
export function pText(value: number | null | undefined): string {
  const text = formatP(value)
  return text.startsWith('<') ? `p ${text}` : `p = ${text}`
}

/** File size for messages: "2.4 MB" or "830 KB". */
export function formatBytes(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  return `${Math.max(1, Math.round(bytes / 1024))} KB`
}
