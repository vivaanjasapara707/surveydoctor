/**
 * The Robustness step: the one analysis the user plans to report (BLUEPRINT §7.6), as a form
 * that becomes the API's analysis JSON. The API runs it on all respondents and without each
 * flag variant; nothing is computed here.
 */
import type { Analysis, SurveySchema } from '../api/client'
import type { ColumnChoice } from './scales'

export type AnalysisKind = Analysis['type']

export interface AnalysisDraft {
  kind: AnalysisKind
  scale: string
  groupColumn: string
  groupA: string
  groupB: string
  scaleX: string
  scaleY: string
}

/** Columns that can split respondents into groups: not a question, not the ID or time
 *  column. Personal columns are already left out of the candidates. */
export function groupColumns(columns: ColumnChoice[], schema: SurveySchema): ColumnChoice[] {
  const used = new Set([...schema.items, schema.id_column, schema.duration_column])
  return columns.filter((c) => !used.has(c.code))
}

/** True when every value of the column is listed by the API, so they can be offered as a
 *  list; otherwise the user types the two values. */
export function valuesListed(column: ColumnChoice | undefined): boolean {
  return column !== undefined && column.values.length === column.nDistinct
}

export function initialAnalysisDraft(
  schema: SurveySchema,
  canGroup: boolean,
  last: Analysis | null,
): AnalysisDraft {
  const scales = Object.keys(schema.scales)
  const empty: AnalysisDraft = {
    kind: canGroup || scales.length < 2 ? 'group_comparison' : 'correlation',
    scale: scales[0] ?? '',
    groupColumn: '',
    groupA: '',
    groupB: '',
    scaleX: scales[0] ?? '',
    scaleY: scales[1] ?? '',
  }
  if (last?.type === 'group_comparison') {
    return {
      ...empty,
      kind: 'group_comparison',
      scale: last.scale,
      groupColumn: last.group_column,
      groupA: String(last.group_a),
      groupB: String(last.group_b),
    }
  }
  if (last?.type === 'correlation') {
    return { ...empty, kind: 'correlation', scaleX: last.scale_x, scaleY: last.scale_y }
  }
  return empty
}

export type AnalysisValidation = { ok: true; analysis: Analysis } | { ok: false; errors: string[] }

/** Plain-English problems in the form; the API checks the analysis again. */
export function validateAnalysis(draft: AnalysisDraft): AnalysisValidation {
  const errors: string[] = []
  if (draft.kind === 'correlation') {
    if (!draft.scaleX || !draft.scaleY) errors.push('Choose the two scales to correlate.')
    else if (draft.scaleX === draft.scaleY) errors.push('Choose two different scales to correlate.')
    if (errors.length > 0) return { ok: false, errors }
    return {
      ok: true,
      analysis: { type: 'correlation', scale_x: draft.scaleX, scale_y: draft.scaleY },
    }
  }

  const a = draft.groupA.trim()
  const b = draft.groupB.trim()
  if (!draft.scale) errors.push('Choose the scale to compare.')
  if (!draft.groupColumn) errors.push('Choose the column that defines the groups.')
  if (!a || !b) errors.push('Choose the two groups to compare.')
  else if (a === b) errors.push('Choose two different group values to compare.')
  if (errors.length > 0) return { ok: false, errors }
  return {
    ok: true,
    analysis: {
      type: 'group_comparison',
      scale: draft.scale,
      group_column: draft.groupColumn,
      group_a: a,
      group_b: b,
    },
  }
}
