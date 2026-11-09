/**
 * The Scales step: which columns are rating questions, how they group into scales, which are
 * reverse-worded, and the answer range. The draft becomes the survey schema sent to the API,
 * which validates it again. Nothing is inferred: reverse-worded questions in particular are
 * only ever marked by the user (BLUEPRINT §6.1).
 */
import type { DurationUnit, InspectResponse, SurveySchema } from '../api/client'
import { parseWhole } from './labels'

export interface ColumnChoice {
  /** Short code used in the schema (e.g. Q1, or the header itself when it is short). */
  code: string
  header: string
  suggested: boolean
  values: string[]
  nDistinct: number
}

export interface DraftScale {
  id: string
  name: string
}

export interface ScaleDraft {
  /** Codes of the columns checked as rating questions. */
  included: string[]
  scales: DraftScale[]
  /** Question code -> scale id. A question belongs to at most one scale. */
  assignment: Record<string, string>
  reverse: string[]
  scaleMin: string
  scaleMax: string
  idColumn: string
  durationColumn: string
  durationUnit: DurationUnit
}

export const DURATION_UNITS: DurationUnit[] = ['seconds', 'minutes', 'milliseconds']

let lastScaleId = 0
export function newScaleId(): string {
  lastScaleId += 1
  return `scale-${lastScaleId}`
}

/** Columns that can be questions, ID or time columns: every column except personal ones. */
export function candidateColumns(inspect: InspectResponse): ColumnChoice[] {
  return inspect.columns
    .filter((c) => c.code !== null && !c.looks_personal)
    .map((c) => ({
      code: c.code as string,
      header: c.header,
      suggested: c.suggested_item,
      values: c.distinct_values,
      nDistinct: c.n_distinct,
    }))
}

/** The draft for a new upload: the suggested rating columns checked, no scales yet, and the
 *  range from the confirmed answer labels if there are any. */
export function emptyDraft(
  columns: ColumnChoice[],
  range: { min: number; max: number } | null,
): ScaleDraft {
  return {
    included: columns.filter((c) => c.suggested).map((c) => c.code),
    scales: [],
    assignment: {},
    reverse: [],
    scaleMin: range ? String(range.min) : '',
    scaleMax: range ? String(range.max) : '',
    idColumn: '',
    durationColumn: '',
    durationUnit: 'seconds',
  }
}

export type DraftFromSchema = { ok: true; draft: ScaleDraft } | { ok: false; error: string }

/** A draft from a schema (the sample's, or a schema file the user loads). */
export function draftFromSchema(schema: SurveySchema, columns: ColumnChoice[]): DraftFromSchema {
  const codes = new Set(columns.map((c) => c.code))
  const used = [
    ...schema.items,
    ...(schema.id_column ? [schema.id_column] : []),
    ...(schema.duration_column ? [schema.duration_column] : []),
  ]
  const missing = used.filter((code) => !codes.has(code))
  if (missing.length > 0) {
    return {
      ok: false,
      error:
        `This schema uses columns that are not in the uploaded file: ${missing.join(', ')}. ` +
        'Load the schema saved for this form, or check that the file is the right export.',
    }
  }

  const scales: DraftScale[] = []
  const assignment: Record<string, string> = {}
  for (const [name, items] of Object.entries(schema.scales)) {
    const scale = { id: newScaleId(), name }
    scales.push(scale)
    for (const item of items) {
      if (assignment[item]) {
        return {
          ok: false,
          error:
            `The question ${item} is in more than one scale. The scale builder keeps each ` +
            'question in one scale; edit the schema file so that it does, and load it again.',
        }
      }
      assignment[item] = scale.id
    }
  }

  return {
    ok: true,
    draft: {
      included: [...schema.items],
      scales,
      assignment,
      reverse: [...schema.reverse_items],
      scaleMin: String(schema.scale_min),
      scaleMax: String(schema.scale_max),
      idColumn: schema.id_column ?? '',
      durationColumn: schema.duration_column ?? '',
      durationUnit: schema.duration_unit ?? 'seconds',
    },
  }
}

/** Questions of a scale, in file order. */
export function scaleItems(draft: ScaleDraft, scaleId: string, columns: ColumnChoice[]): string[] {
  return columns
    .map((c) => c.code)
    .filter((code) => draft.included.includes(code) && draft.assignment[code] === scaleId)
}

/** Include or leave out a question; leaving it out also clears its scale and reverse mark. */
export function setIncluded(draft: ScaleDraft, code: string, included: boolean): ScaleDraft {
  if (included) {
    return draft.included.includes(code) ? draft : { ...draft, included: [...draft.included, code] }
  }
  const assignment = { ...draft.assignment }
  delete assignment[code]
  return {
    ...draft,
    included: draft.included.filter((c) => c !== code),
    assignment,
    reverse: draft.reverse.filter((c) => c !== code),
  }
}

export function removeScale(draft: ScaleDraft, scaleId: string): ScaleDraft {
  const assignment = Object.fromEntries(
    Object.entries(draft.assignment).filter(([, id]) => id !== scaleId),
  )
  return { ...draft, scales: draft.scales.filter((s) => s.id !== scaleId), assignment }
}

/** Plain-English problems that stop the checks from running. The API validates again. */
export function validateDraft(
  draft: ScaleDraft,
  columns: ColumnChoice[],
  labelMap: Record<string, number> | null,
): string[] {
  const errors: string[] = []
  if (draft.included.length < 2) errors.push('Select at least two questions to check.')

  const min = parseWhole(draft.scaleMin)
  const max = parseWhole(draft.scaleMax)
  if (min === null || max === null) {
    errors.push('Enter the lowest and highest answer of the scale as whole numbers, e.g. 1 and 5.')
  } else if (min >= max) {
    errors.push(`The lowest answer (${min}) must be smaller than the highest answer (${max}).`)
  } else if (labelMap) {
    const outside = Object.entries(labelMap).filter(([, v]) => v < min || v > max)
    if (outside.length > 0) {
      errors.push(
        `The answer labels use numbers outside the range ${min}–${max} (for example “${outside[0][0]}” is ` +
          `${outside[0][1]}). Change the range, or go back and change the answer labels.`,
      )
    }
  }

  if (draft.scales.length === 0) {
    errors.push('Create at least one scale and choose its questions.')
  }
  const seen = new Map<string, string>()
  for (const [index, scale] of draft.scales.entries()) {
    const name = scale.name.trim()
    if (!name) {
      errors.push(`Give scale ${index + 1} a name.`)
      continue
    }
    const key = name.toLowerCase()
    if (seen.has(key)) {
      errors.push(`Two scales are called “${name}”. Scale names must be different.`)
    }
    seen.set(key, name)
    const n = scaleItems(draft, scale.id, columns).length
    if (n < 2) {
      errors.push(
        `“${name}” has ${n === 0 ? 'no questions' : '1 question'}. A scale needs at least 2.`,
      )
    }
  }

  if (draft.idColumn && draft.idColumn === draft.durationColumn) {
    errors.push('The ID column and the completion-time column must be different columns.')
  }
  return errors
}

/** The schema sent to the API. Call only when validateDraft returned no errors. */
export function buildSchema(
  draft: ScaleDraft,
  columns: ColumnChoice[],
  questionText: Record<string, string>,
  labelMap: Record<string, number> | null,
): SurveySchema {
  const order = columns.map((c) => c.code)
  const items = order.filter((code) => draft.included.includes(code))
  const scales = Object.fromEntries(
    draft.scales.map((s) => [s.name.trim(), scaleItems(draft, s.id, columns)]),
  )
  // Short codes stand in for long headers; the API renames the columns with this map.
  const renamed = Object.entries(questionText).some(([code, header]) => code !== header)
  return {
    items,
    scales,
    reverse_items: items.filter((code) => draft.reverse.includes(code)),
    scale_min: Number(draft.scaleMin),
    scale_max: Number(draft.scaleMax),
    id_column: draft.idColumn || null,
    duration_column: draft.durationColumn || null,
    duration_unit: draft.durationUnit,
    label_map: labelMap,
    question_text: renamed ? questionText : null,
  }
}

/** Whole-number answers seen in the checked question columns, to help set the range. */
export function numericAnswers(draft: ScaleDraft, columns: ColumnChoice[]): number[] {
  const values = new Set<number>()
  for (const column of columns) {
    if (!draft.included.includes(column.code)) continue
    for (const value of column.values) {
      const number = parseWhole(value)
      if (number !== null) values.add(number)
    }
  }
  return [...values].sort((a, b) => a - b)
}
