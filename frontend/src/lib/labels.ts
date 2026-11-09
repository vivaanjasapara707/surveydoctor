/**
 * The answer-label step: turn the API's proposed label map into an editable draft, and check
 * the draft before it becomes part of the schema. No statistics here; the API proposes the
 * map and validates it again when the checks run.
 */
import type { LabelDetection } from '../api/client'

/** A number on the scale, 'missing' (not a rating answer), or null (not chosen yet). */
export type LabelValue = number | 'missing' | null

export interface LabelRow {
  /** The label as it is sent in the schema's label_map. */
  key: string
  /** True for labels the API recognised; false for labels the user must map. */
  recognised: boolean
  value: LabelValue
}

export interface LabelDraft {
  rows: LabelRow[]
  /** Kept as typed, so the inputs can be empty while the user edits them. */
  scaleMin: string
  scaleMax: string
}

export interface LabelChoice {
  labelMap: Record<string, number>
  scaleMin: number
  scaleMax: number
  /** Labels the user marked as not a rating answer; they are counted as missing answers. */
  notRatings: string[]
}

export type LabelValidation = { ok: true; choice: LabelChoice } | { ok: false; errors: string[] }

/** The label step is needed when the answers contain text labels the API found. */
export function labelsNeeded(labels: LabelDetection): boolean {
  return labels.label_map !== null || labels.unrecognised.length > 0
}

/** "agreement_5" -> "agreement labels, 5 points". */
export function labelSetName(name: string): string {
  const match = /^([a-z]+)_(\d+)$/.exec(name)
  if (!match) return name.replace(/_/g, ' ')
  return `${match[1]} labels, ${match[2]} points`
}

/** The draft to start from: the confirmed choice if there is one, else the API's proposal. */
export function initialDraft(labels: LabelDetection, confirmed: LabelChoice | null): LabelDraft {
  const proposed = labels.label_map ?? {}
  const recognised: LabelRow[] = Object.entries(proposed).map(([key, value]) => ({
    key,
    recognised: true,
    value: confirmed ? (confirmed.labelMap[key] ?? null) : value,
  }))
  recognised.sort((a, b) => sortValue(a.value) - sortValue(b.value) || a.key.localeCompare(b.key))

  const unrecognised: LabelRow[] = labels.unrecognised.map((key) => ({
    key,
    recognised: false,
    value: confirmed
      ? (confirmed.labelMap[key] ?? (confirmed.notRatings.includes(key) ? 'missing' : null))
      : null,
  }))

  const scaleMin = confirmed?.scaleMin ?? labels.scale_min
  const scaleMax = confirmed?.scaleMax ?? labels.scale_max
  return {
    rows: [...recognised, ...unrecognised],
    scaleMin: scaleMin === null ? '' : String(scaleMin),
    scaleMax: scaleMax === null ? '' : String(scaleMax),
  }
}

function sortValue(value: LabelValue): number {
  return typeof value === 'number' ? value : Number.POSITIVE_INFINITY
}

function parseWhole(text: string): number | null {
  const trimmed = text.trim()
  if (!/^-?\d+$/.test(trimmed)) return null
  return Number(trimmed)
}

/** The scale range typed by the user, or null while it is incomplete or invalid. */
export function parseRange(draft: LabelDraft): { min: number; max: number } | null {
  const min = parseWhole(draft.scaleMin)
  const max = parseWhole(draft.scaleMax)
  if (min === null || max === null || min >= max) return null
  return { min, max }
}

/** Numbers offered for each label: every whole number in the scale range. */
export function rangeOptions(draft: LabelDraft): number[] {
  const range = parseRange(draft)
  if (!range) return []
  return Array.from({ length: range.max - range.min + 1 }, (_, i) => range.min + i)
}

/** Check the draft; on success return the label map and range for the schema. */
export function validateLabels(draft: LabelDraft): LabelValidation {
  const errors: string[] = []
  const min = parseWhole(draft.scaleMin)
  const max = parseWhole(draft.scaleMax)
  if (min === null || max === null) {
    errors.push('Enter the lowest and highest answer of the scale as whole numbers, e.g. 1 and 5.')
  } else if (min >= max) {
    errors.push(`The lowest answer (${min}) must be smaller than the highest answer (${max}).`)
  }
  const range = parseRange(draft)

  for (const row of draft.rows) {
    if (row.value === null) {
      errors.push(`Choose a number for “${row.key}”, or mark it as not a rating answer.`)
    } else if (range && typeof row.value === 'number') {
      if (row.value < range.min || row.value > range.max) {
        errors.push(
          `“${row.key}” is set to ${row.value}, outside the scale range ${range.min}–${range.max}.`,
        )
      }
    }
  }

  if (errors.length > 0 || !range) return { ok: false, errors }
  const labelMap: Record<string, number> = {}
  const notRatings: string[] = []
  for (const row of draft.rows) {
    if (typeof row.value === 'number') labelMap[row.key] = row.value
    else notRatings.push(row.key)
  }
  return { ok: true, choice: { labelMap, scaleMin: range.min, scaleMax: range.max, notRatings } }
}
