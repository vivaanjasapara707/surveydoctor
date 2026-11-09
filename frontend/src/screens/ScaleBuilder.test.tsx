import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { candidateColumns, draftFromSchema, emptyDraft, type ScaleDraft } from '../lib/scales'
import type { LoadStatus } from '../lib/upload'
import { inspectBfi, inspectGoogleForms, sampleSchemaBfi } from '../test/fixtures'
import { ScaleBuilder } from './ScaleBuilder'

const formsColumns = candidateColumns(inspectGoogleForms)
const labelMap = { 'strongly disagree': 1, disagree: 2, agree: 4, 'strongly agree': 5 }

/** The builder with its draft held in state, as App holds it. */
function setup({
  initial = emptyDraft(formsColumns, { min: 1, max: 5 }),
  status = { kind: 'idle' } as LoadStatus,
  columns = formsColumns,
  questionText = inspectGoogleForms.question_text,
  map = labelMap as Record<string, number> | null,
} = {}) {
  const onRun = vi.fn()
  const onBack = vi.fn()
  function Harness() {
    const [draft, setDraft] = useState<ScaleDraft>(initial)
    return (
      <ScaleBuilder
        columns={columns}
        questionText={questionText}
        draft={draft}
        onChange={setDraft}
        labelMap={map}
        status={status}
        isSample={false}
        onRun={onRun}
        onBack={onBack}
        backLabel="Back to answer labels"
      />
    )
  }
  render(<Harness />)
  return { onRun, onBack }
}

const run = () => fireEvent.click(screen.getByRole('button', { name: 'Run checks' }))

function addScale(name: string) {
  fireEvent.click(screen.getByRole('button', { name: 'Add a scale' }))
  const inputs = screen.getAllByRole('textbox', { name: /^Name of scale/ })
  fireEvent.change(inputs[inputs.length - 1], { target: { value: name } })
}

function assign(code: string, scale: string) {
  const select = screen.getByRole('combobox', { name: `Scale for ${code}` })
  const option = within(select).getByRole('option', { name: scale }) as HTMLOptionElement
  fireEvent.change(select, { target: { value: option.value } })
}

describe('ScaleBuilder', () => {
  it('ticks the suggested rating questions', () => {
    setup()
    expect(screen.getByRole('checkbox', { name: /^Q1\s*I enjoy working in teams/ })).toBeChecked()
    expect(screen.getByRole('checkbox', { name: /^Q8\s*How old are you/ })).not.toBeChecked()
    expect(screen.getByRole('checkbox', { name: /^Timestamp$/ })).not.toBeChecked()
    expect(screen.getByText(/7 questions ticked, 7 without a scale/)).toBeInTheDocument()
  })

  it('builds a scale and sends the schema', () => {
    const { onRun } = setup()
    addScale('Teamwork')
    for (const code of ['Q1', 'Q2', 'Q3', 'Q4']) assign(code, 'Teamwork')
    fireEvent.click(screen.getByRole('checkbox', { name: 'Q2 is reverse-worded' }))
    expect(screen.getByText('4 questions')).toBeInTheDocument()

    run()
    expect(onRun).toHaveBeenCalledTimes(1)
    const schema = onRun.mock.calls[0][0]
    expect(schema.scales).toEqual({ Teamwork: ['Q1', 'Q2', 'Q3', 'Q4'] })
    expect(schema.reverse_items).toEqual(['Q2'])
    expect(schema.items).toEqual(['Q1', 'Q2', 'Q3', 'Q4', 'Q5', 'Q6', 'Q7'])
    expect(schema.label_map).toEqual(labelMap)
    expect([schema.scale_min, schema.scale_max]).toEqual([1, 5])
  })

  it('does not run while a scale has fewer than two questions', () => {
    const { onRun } = setup()
    addScale('Teamwork')
    assign('Q1', 'Teamwork')
    run()
    expect(onRun).not.toHaveBeenCalled()
    expect(screen.getByRole('alert')).toHaveTextContent(
      '“Teamwork” has 1 question. A scale needs at least 2.',
    )
  })

  it('does not run without any scale', () => {
    const { onRun } = setup()
    run()
    expect(onRun).not.toHaveBeenCalled()
    expect(screen.getByRole('alert')).toHaveTextContent(
      'Create at least one scale and choose its questions.',
    )
  })

  it('unticking a question takes it out of its scale', () => {
    setup()
    addScale('Teamwork')
    assign('Q1', 'Teamwork')
    assign('Q2', 'Teamwork')
    expect(screen.getByText('2 questions')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('checkbox', { name: /^Q2\s*I prefer to work alone/ }))
    expect(screen.getByText('1 question')).toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: 'Scale for Q2' })).toBeDisabled()
    expect(screen.getByRole('checkbox', { name: 'Q2 is reverse-worded' })).toBeDisabled()
  })

  it('removes a scale', () => {
    setup()
    addScale('Teamwork')
    fireEvent.click(screen.getByRole('button', { name: 'Remove Teamwork' }))
    expect(screen.queryByRole('textbox', { name: /^Name of scale/ })).not.toBeInTheDocument()
  })

  it('offers only non-question columns as ID or time column', () => {
    setup()
    const id = screen.getByRole('combobox', { name: 'Respondent ID' })
    const options = within(id)
      .getAllByRole('option')
      .map((o) => o.textContent)
    expect(options).toEqual([
      'None',
      'Timestamp',
      'Q8: How old are you?',
      'Q9: Any other comments?',
    ])
  })

  it('shows the answers seen when there are no labels', () => {
    const columns = candidateColumns(inspectBfi)
    setup({
      columns,
      questionText: inspectBfi.question_text,
      map: null,
      initial: emptyDraft(columns, null),
    })
    expect(
      screen.getByText(/Answers seen in the ticked questions: 1, 2, 3, 4, 5, 6\./),
    ).toBeInTheDocument()
  })

  it('loads a schema file', async () => {
    const columns = candidateColumns(inspectBfi)
    setup({
      columns,
      questionText: inspectBfi.question_text,
      map: null,
      initial: emptyDraft(columns, null),
    })
    const file = new File([JSON.stringify(sampleSchemaBfi)], 'bfi_schema.json', {
      type: 'application/json',
    })
    fireEvent.change(screen.getByLabelText('Load a schema file'), { target: { files: [file] } })
    await waitFor(() =>
      expect(screen.getAllByRole('textbox', { name: /^Name of scale/ })).toHaveLength(5),
    )
    expect(screen.getByRole('checkbox', { name: 'A1 is reverse-worded' })).toBeChecked()
    expect(screen.getByRole('combobox', { name: 'Respondent ID' })).toHaveValue('id')
  })

  it('refuses a schema file for another form', async () => {
    setup()
    const file = new File([JSON.stringify(sampleSchemaBfi)], 'bfi_schema.json')
    fireEvent.change(screen.getByLabelText('Load a schema file'), { target: { files: [file] } })
    expect(await screen.findByRole('alert')).toHaveTextContent(
      /This schema uses columns that are not in the uploaded file: A1/,
    )
  })

  it('starts from the sample schema', () => {
    const columns = candidateColumns(inspectBfi)
    const result = draftFromSchema(sampleSchemaBfi, columns)
    if (!result.ok) throw new Error(result.error)
    const { onRun } = setup({
      columns,
      questionText: inspectBfi.question_text,
      map: null,
      initial: result.draft,
    })
    run()
    expect(onRun.mock.calls[0][0]).toEqual({ ...sampleSchemaBfi, label_map: null })
  })

  it('shows progress and API errors', () => {
    setup({
      status: {
        kind: 'error',
        title: 'The checks could not run',
        message: "Label 'agree' maps to 4, which is outside the scale range 1–3.",
      },
    })
    expect(screen.getByRole('alert')).toHaveTextContent('outside the scale range 1–3')
  })

  it('disables the buttons while the checks run', () => {
    setup({
      status: { kind: 'loading', message: 'Running checks on 12 respondents…', waking: false },
    })
    expect(screen.getByRole('status')).toHaveTextContent('Running checks on 12 respondents…')
    expect(screen.getByRole('button', { name: 'Run checks' })).toBeDisabled()
  })
})
