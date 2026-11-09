const whole = new Intl.NumberFormat('en-GB', { maximumFractionDigits: 0 })

/** 2800 -> "2,800". */
export function formatCount(value: number): string {
  return whole.format(value)
}

/** "1 respondent" / "2 respondents". */
export function plural(count: number, singular: string, pluralForm = `${singular}s`): string {
  return `${formatCount(count)} ${count === 1 ? singular : pluralForm}`
}

/** File size for messages: "2.4 MB" or "830 KB". */
export function formatBytes(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  return `${Math.max(1, Math.round(bytes / 1024))} KB`
}
