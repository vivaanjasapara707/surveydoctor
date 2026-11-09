import { describe, expect, it } from 'vitest'
import { googleFormsLabels, unknownLabels } from '../test/fixtures'
import {
  initialDraft,
  labelSetName,
  labelsNeeded,
  rangeOptions,
  validateLabels,
  type LabelDraft,
} from './labels'

function withValue(draft: LabelDraft, key: string, value: LabelDraft['rows'][number]['value']) {
  return { ...draft, rows: draft.rows.map((r) => (r.key === key ? { ...r, value } : r)) }
}

describe('labelsNeeded', () => {
  it('is true when the API proposed a label map or found unrecognised labels', () => {
    expect(labelsNeeded(googleFormsLabels)).toBe(true)
    expect(labelsNeeded(unknownLabels)).toBe(true)
  })

  it('is false for numeric answers', () => {
    expect(
      labelsNeeded({ ...unknownLabels, unrecognised: [], label_map: null, label_set: null }),
    ).toBe(false)
  })
})

describe('labelSetName', () => {
  it('turns the API name into words', () => {
    expect(labelSetName('agreement_5')).toBe('agreement labels, 5 points')
    expect(labelSetName('frequency_7')).toBe('frequency labels, 7 points')
  })
})

describe('initialDraft', () => {
  it('starts from the proposal, sorted by number, with unrecognised labels unset', () => {
    const draft = initialDraft(googleFormsLabels, null)
    expect(draft.scaleMin).toBe('1')
    expect(draft.scaleMax).toBe('5')
    expect(draft.rows.map((r) => [r.key, r.value])).toEqual([
      ['strongly disagree', 1],
      ['disagree', 2],
      ['neither agree nor disagree', 3],
      ['neutral', 3],
      ['agree', 4],
      ['strongly agree', 5],
      ['Strongly agre', null],
    ])
    expect(draft.rows.at(-1)?.recognised).toBe(false)
  })

  it('starts from a confirmed choice when there is one', () => {
    const draft = initialDraft(googleFormsLabels, {
      labelMap: { ...googleFormsLabels.label_map, agree: 5 },
      scaleMin: 1,
      scaleMax: 7,
      notRatings: ['Strongly agre'],
    })
    expect(draft.scaleMax).toBe('7')
    expect(draft.rows.find((r) => r.key === 'agree')?.value).toBe(5)
    expect(draft.rows.find((r) => r.key === 'Strongly agre')?.value).toBe('missing')
  })

  it('leaves the range empty when the API could not propose one', () => {
    const draft = initialDraft(unknownLabels, null)
    expect(draft.scaleMin).toBe('')
    expect(draft.scaleMax).toBe('')
    expect(rangeOptions(draft)).toEqual([])
  })
})

describe('validateLabels', () => {
  const start = initialDraft(googleFormsLabels, null)

  it('refuses unmapped labels; they are never guessed', () => {
    const result = validateLabels(start)
    expect(result).toEqual({
      ok: false,
      errors: ['Choose a number for “Strongly agre”, or mark it as not a rating answer.'],
    })
  })

  it('returns the label map once every label has a number', () => {
    const result = validateLabels(withValue(start, 'Strongly agre', 5))
    expect(result.ok).toBe(true)
    if (result.ok) {
      expect(result.choice).toEqual({
        labelMap: { ...googleFormsLabels.label_map, 'Strongly agre': 5 },
        scaleMin: 1,
        scaleMax: 5,
        notRatings: [],
      })
    }
  })

  it('leaves labels marked as not a rating out of the map', () => {
    const result = validateLabels(withValue(start, 'Strongly agre', 'missing'))
    expect(result.ok && result.choice.notRatings).toEqual(['Strongly agre'])
    expect(result.ok && 'Strongly agre' in result.choice.labelMap).toBe(false)
  })

  it('refuses numbers outside the scale range', () => {
    const draft = { ...withValue(start, 'Strongly agre', 5), scaleMax: '4' }
    expect(validateLabels(draft)).toEqual({
      ok: false,
      errors: [
        '“strongly agree” is set to 5, outside the scale range 1–4.',
        '“Strongly agre” is set to 5, outside the scale range 1–4.',
      ],
    })
  })

  it('refuses a missing or reversed range', () => {
    const empty = validateLabels({ ...start, scaleMin: '' })
    expect(!empty.ok && empty.errors[0]).toMatch(/Enter the lowest and highest answer/)
    const reversed = validateLabels({ ...start, scaleMin: '5', scaleMax: '1' })
    expect(!reversed.ok && reversed.errors[0]).toBe(
      'The lowest answer (5) must be smaller than the highest answer (1).',
    )
    const fraction = validateLabels({ ...start, scaleMax: '4.5' })
    expect(fraction.ok).toBe(false)
  })
})
