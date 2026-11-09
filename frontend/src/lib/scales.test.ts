import { describe, expect, it } from 'vitest'
import { inspectBfi, inspectGoogleForms, sampleSchemaBfi } from '../test/fixtures'
import {
  buildSchema,
  candidateColumns,
  draftFromSchema,
  emptyDraft,
  numericAnswers,
  removeScale,
  setIncluded,
  validateDraft,
  type ScaleDraft,
} from './scales'

const formsColumns = candidateColumns(inspectGoogleForms)
const bfiColumns = candidateColumns(inspectBfi)

function teamwork(): ScaleDraft {
  const draft = emptyDraft(formsColumns, { min: 1, max: 5 })
  const scale = { id: 'team', name: 'Teamwork' }
  return {
    ...draft,
    scales: [scale],
    assignment: { Q1: 'team', Q2: 'team', Q3: 'team', Q4: 'team' },
    reverse: ['Q2'],
  }
}

describe('candidateColumns', () => {
  it('leaves out personal columns', () => {
    const headers = formsColumns.map((c) => c.header)
    expect(headers).not.toContain('Email Address')
    expect(headers).not.toContain('Your name')
    expect(formsColumns.map((c) => c.code)).toEqual([
      'Timestamp',
      'Q1',
      'Q2',
      'Q3',
      'Q4',
      'Q5',
      'Q6',
      'Q7',
      'Q8',
      'Q9',
    ])
  })
})

describe('emptyDraft', () => {
  it('ticks the columns the API suggested and takes the range from the labels', () => {
    const draft = emptyDraft(formsColumns, { min: 1, max: 5 })
    expect(draft.included).toEqual(['Q1', 'Q2', 'Q3', 'Q4', 'Q5', 'Q6', 'Q7'])
    expect(draft.scales).toEqual([])
    expect(draft.reverse).toEqual([])
    expect([draft.scaleMin, draft.scaleMax]).toEqual(['1', '5'])
  })

  it('leaves the range empty without labels', () => {
    const draft = emptyDraft(bfiColumns, null)
    expect([draft.scaleMin, draft.scaleMax]).toEqual(['', ''])
  })
})

describe('draftFromSchema and buildSchema', () => {
  it('round-trips the sample schema', () => {
    const result = draftFromSchema(sampleSchemaBfi, bfiColumns)
    expect(result.ok).toBe(true)
    if (!result.ok) return
    expect(result.draft.reverse).toEqual(['A1', 'C4', 'C5', 'E1', 'E2', 'O2', 'O5'])
    expect(result.draft.idColumn).toBe('id')
    const schema = buildSchema(result.draft, bfiColumns, inspectBfi.question_text, null)
    expect(schema).toEqual({ ...sampleSchemaBfi, label_map: null, question_text: null })
  })

  it('refuses a schema for a different file', () => {
    const result = draftFromSchema(sampleSchemaBfi, formsColumns)
    expect(result.ok).toBe(false)
    expect(!result.ok && result.error).toMatch(/^This schema uses columns that are not in the/)
  })

  it('refuses a question in two scales', () => {
    const schema = { ...sampleSchemaBfi, scales: { One: ['A1', 'A2'], Two: ['A2', 'A3'] } }
    const result = draftFromSchema(schema, bfiColumns)
    expect(!result.ok && result.error).toMatch(/A2 is in more than one scale/)
  })

  it('sends short codes with the original headers, and the confirmed labels', () => {
    const labelMap = { agree: 4, 'Strongly agre': 5 }
    const schema = buildSchema(teamwork(), formsColumns, inspectGoogleForms.question_text, labelMap)
    expect(schema.items).toEqual(['Q1', 'Q2', 'Q3', 'Q4', 'Q5', 'Q6', 'Q7'])
    expect(schema.scales).toEqual({ Teamwork: ['Q1', 'Q2', 'Q3', 'Q4'] })
    expect(schema.reverse_items).toEqual(['Q2'])
    expect(schema.label_map).toBe(labelMap)
    expect(schema.question_text?.Q1).toBe('I enjoy working in teams.')
    expect(schema.id_column).toBeNull()
  })
})

describe('editing', () => {
  it('clears the scale and reverse mark of a question that is unticked', () => {
    const draft = setIncluded(teamwork(), 'Q2', false)
    expect(draft.included).not.toContain('Q2')
    expect(draft.assignment).not.toHaveProperty('Q2')
    expect(draft.reverse).toEqual([])
  })

  it('removing a scale frees its questions', () => {
    const draft = removeScale(teamwork(), 'team')
    expect(draft.scales).toEqual([])
    expect(draft.assignment).toEqual({})
  })

  it('lists the whole-number answers seen in ticked questions', () => {
    expect(numericAnswers(emptyDraft(bfiColumns, null), bfiColumns)).toEqual([1, 2, 3, 4, 5, 6])
  })
})

describe('validateDraft', () => {
  it('accepts a complete draft', () => {
    expect(validateDraft(teamwork(), formsColumns, { agree: 4 })).toEqual([])
  })

  it('needs a scale with at least two questions', () => {
    expect(validateDraft(emptyDraft(formsColumns, { min: 1, max: 5 }), formsColumns, null)).toEqual(
      ['Create at least one scale and choose its questions.'],
    )
    const one = { ...teamwork(), assignment: { Q1: 'team' } }
    expect(validateDraft(one, formsColumns, null)).toEqual([
      '“Teamwork” has 1 question. A scale needs at least 2.',
    ])
  })

  it('needs different, non-empty scale names', () => {
    const draft = {
      ...teamwork(),
      scales: [
        { id: 'team', name: 'Teamwork' },
        { id: 'b', name: ' teamwork ' },
        { id: 'c', name: '' },
      ],
      assignment: { Q1: 'team', Q2: 'team', Q3: 'b', Q4: 'b' },
    }
    expect(validateDraft(draft, formsColumns, null)).toEqual([
      'Two scales are called “teamwork”. Scale names must be different.',
      'Give scale 3 a name.',
    ])
  })

  it('checks the range, also against the confirmed labels', () => {
    const empty = { ...teamwork(), scaleMax: '' }
    expect(validateDraft(empty, formsColumns, null)[0]).toMatch(/Enter the lowest and highest/)
    const narrow = { ...teamwork(), scaleMax: '4' }
    expect(validateDraft(narrow, formsColumns, { 'strongly agree': 5 })).toEqual([
      'The answer labels use numbers outside the range 1–4 (for example “strongly agree” is 5). ' +
        'Change the range, or go back and change the answer labels.',
    ])
  })

  it('needs at least two questions and distinct ID and time columns', () => {
    const draft = { ...teamwork(), idColumn: 'Q8', durationColumn: 'Q8' }
    expect(validateDraft(draft, formsColumns, null)).toEqual([
      'The ID column and the completion-time column must be different columns.',
    ])
    const few = { ...emptyDraft(formsColumns, { min: 1, max: 5 }), included: ['Q1'] }
    expect(validateDraft(few, formsColumns, null)[0]).toBe(
      'Select at least two questions to check.',
    )
  })
})
