import { describe, expect, it } from 'vitest'
import { inspectBfi, sampleSchemaBfi } from '../test/fixtures'
import {
  groupColumns,
  initialAnalysisDraft,
  validateAnalysis,
  valuesListed,
  type AnalysisDraft,
} from './robustness'
import { candidateColumns } from './scales'

const columns = candidateColumns(inspectBfi)

const groupDraft: AnalysisDraft = {
  kind: 'group_comparison',
  scale: 'Agreeableness',
  groupColumn: 'gender',
  groupA: '1',
  groupB: '2',
  scaleX: 'Agreeableness',
  scaleY: 'Conscientiousness',
}

describe('groupColumns', () => {
  it('offers the columns that are not questions, ID or time', () => {
    expect(groupColumns(columns, sampleSchemaBfi).map((c) => c.code)).toEqual([
      'gender',
      'education',
      'age',
    ])
  })

  it('knows when every value of a column is listed', () => {
    const [gender, , age] = groupColumns(columns, sampleSchemaBfi)
    expect(valuesListed(gender)).toBe(true)
    expect(gender.values).toEqual(['1', '2'])
    // Age has 64 different values; the API lists the first 20.
    expect(valuesListed(age)).toBe(false)
  })
})

describe('initialAnalysisDraft', () => {
  it('starts with a group comparison on the first scale, with no groups chosen', () => {
    expect(initialAnalysisDraft(sampleSchemaBfi, true, null)).toEqual({
      kind: 'group_comparison',
      scale: 'Agreeableness',
      groupColumn: '',
      groupA: '',
      groupB: '',
      scaleX: 'Agreeableness',
      scaleY: 'Conscientiousness',
    })
  })

  it('starts with a correlation when there is nothing to group by', () => {
    expect(initialAnalysisDraft(sampleSchemaBfi, false, null).kind).toBe('correlation')
  })

  it('starts from the last analysis', () => {
    const draft = initialAnalysisDraft(sampleSchemaBfi, true, {
      type: 'correlation',
      scale_x: 'Neuroticism',
      scale_y: 'Extraversion',
    })
    expect([draft.kind, draft.scaleX, draft.scaleY]).toEqual([
      'correlation',
      'Neuroticism',
      'Extraversion',
    ])
  })
})

describe('validateAnalysis', () => {
  it('builds the group comparison sent to the API', () => {
    expect(validateAnalysis(groupDraft)).toEqual({
      ok: true,
      analysis: {
        type: 'group_comparison',
        scale: 'Agreeableness',
        group_column: 'gender',
        group_a: '1',
        group_b: '2',
      },
    })
  })

  it('needs a column and two different groups', () => {
    expect(validateAnalysis({ ...groupDraft, groupColumn: '', groupA: '', groupB: '' })).toEqual({
      ok: false,
      errors: ['Choose the column that defines the groups.', 'Choose the two groups to compare.'],
    })
    expect(validateAnalysis({ ...groupDraft, groupB: ' 1 ' })).toEqual({
      ok: false,
      errors: ['Choose two different group values to compare.'],
    })
  })

  it('needs two different scales to correlate', () => {
    const draft = { ...groupDraft, kind: 'correlation' as const }
    expect(validateAnalysis(draft)).toEqual({
      ok: true,
      analysis: { type: 'correlation', scale_x: 'Agreeableness', scale_y: 'Conscientiousness' },
    })
    expect(validateAnalysis({ ...draft, scaleY: 'Agreeableness' })).toEqual({
      ok: false,
      errors: ['Choose two different scales to correlate.'],
    })
  })
})
