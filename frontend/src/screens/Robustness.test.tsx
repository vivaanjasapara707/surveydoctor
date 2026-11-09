import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { LoadStatus } from '../lib/upload'
import { candidateColumns } from '../lib/scales'
import {
  inspectBfi,
  robustnessCorrelation,
  robustnessGender,
  robustnessUnstable,
  sampleSchemaBfi,
} from '../test/fixtures'
import { Robustness } from './Robustness'

const columns = candidateColumns(inspectBfi)
const file = new File(['id,A1\n'], 'bfi.csv', { type: 'text/csv' })

function setup({
  result = null as Parameters<typeof Robustness>[0]['result'],
  status = { kind: 'idle' } as LoadStatus,
  schema = sampleSchemaBfi,
} = {}) {
  const onRun = vi.fn()
  const onBack = vi.fn()
  render(
    <Robustness
      file={file}
      schema={schema}
      columns={columns}
      result={result}
      status={status}
      onRun={onRun}
      onBack={onBack}
    />,
  )
  return { onRun, onBack }
}

const run = () => fireEvent.click(screen.getByRole('button', { name: 'Run robustness check' }))
const choose = (label: string, value: string) =>
  fireEvent.change(screen.getByLabelText(label), { target: { value } })

describe('Robustness', () => {
  it('sends a group comparison with the chosen groups', () => {
    const { onRun } = setup()
    choose('Column that defines the groups', 'gender')
    expect(
      within(screen.getByLabelText('Group A'))
        .getAllByRole('option')
        .map((o) => o.textContent),
    ).toEqual(['Choose…', '1', '2'])
    choose('Group A', '1')
    choose('Group B', '2')
    run()
    expect(onRun).toHaveBeenCalledWith({
      type: 'group_comparison',
      scale: 'Agreeableness',
      group_column: 'gender',
      group_a: '1',
      group_b: '2',
    })
  })

  it('does not run without groups', () => {
    const { onRun } = setup()
    run()
    expect(onRun).not.toHaveBeenCalled()
    expect(screen.getByRole('alert')).toHaveTextContent(
      'Choose the column that defines the groups.',
    )
  })

  it('asks for typed values when a column has too many to list', () => {
    setup()
    choose('Column that defines the groups', 'age')
    expect(screen.getByLabelText('Group A').tagName).toBe('INPUT')
    expect(screen.getByText(/type the two values exactly/)).toBeInTheDocument()
  })

  it('sends a correlation between two scales', () => {
    const { onRun } = setup()
    fireEvent.click(screen.getByRole('radio', { name: /Correlate two scales/ }))
    choose('First scale', 'Neuroticism')
    choose('Second scale', 'Extraversion')
    run()
    expect(onRun).toHaveBeenCalledWith({
      type: 'correlation',
      scale_x: 'Neuroticism',
      scale_y: 'Extraversion',
    })
  })

  it('explains why a kind of analysis is not available', () => {
    const schema = {
      ...sampleSchemaBfi,
      items: [...sampleSchemaBfi.items, 'gender', 'education', 'age'],
      scales: { Agreeableness: sampleSchemaBfi.scales.Agreeableness },
    }
    setup({ schema })
    expect(screen.getByRole('radio', { name: /Compare two groups/ })).toBeDisabled()
    expect(screen.getByRole('radio', { name: /Correlate two scales/ })).toBeDisabled()
    expect(screen.getByText(/no other column to form groups with/)).toBeInTheDocument()
    expect(screen.getByText(/it needs at least two scales/)).toBeInTheDocument()
  })

  it('shows the variant table and the verdict from the API', () => {
    setup({
      result: { analysis: robustnessGender.robustness.analysis, response: robustnessGender },
    })
    expect(screen.getByText(robustnessGender.robustness.sentence)).toBeInTheDocument()
    const table = screen.getByRole('table')
    const rows = within(table).getAllByRole('row')
    expect(rows).toHaveLength(5)
    expect(rows[1]).toHaveTextContent(/All respondents\s*2,790\s*A 917 · B 1,873\s*-0\.40/)
    expect(rows[2]).toHaveTextContent('686 left out')
    expect(within(table).queryByText('⚠ changed')).not.toBeInTheDocument()
    // The form starts from the analysis that was checked.
    expect(screen.getByLabelText('Column that defines the groups')).toHaveValue('gender')
  })

  it('marks a variant that changed the result with a word', () => {
    setup({
      result: { analysis: robustnessUnstable.robustness.analysis, response: robustnessUnstable },
    })
    const changed = screen.getByRole('row', { name: /Excluding respondents flagged by any rule/ })
    expect(changed).toHaveTextContent('⚠ changed')
    expect(screen.getByText('Serious concern')).toBeInTheDocument()
  })

  it('labels the correlation columns from the API', () => {
    setup({
      result: {
        analysis: robustnessCorrelation.robustness.analysis,
        response: robustnessCorrelation,
      },
    })
    const headers = within(screen.getByRole('table'))
      .getAllByRole('columnheader')
      .map((h) => h.textContent)
    expect(headers).toContain('Pearson r')
    expect(headers).toContain("Spearman's rho")
    // For a correlation the effect size is r itself, so it is not repeated.
    expect(headers.filter((h) => h === 'r')).toHaveLength(0)
  })

  it('shows progress, the wake-up message and errors', () => {
    setup({ status: { kind: 'loading', message: 'Running the analysis…', waking: true } })
    expect(screen.getAllByRole('status')[0]).toHaveTextContent(/Starting the analysis server/)
    expect(screen.getByRole('button', { name: 'Run robustness check' })).toBeDisabled()
  })

  it("shows the API's error", () => {
    setup({
      status: {
        kind: 'error',
        title: 'The robustness check could not run',
        message: "No respondent has the value '3' in column 'gender'.",
      },
    })
    expect(screen.getByRole('alert')).toHaveTextContent("No respondent has the value '3'")
  })
})

describe('Robustness result', () => {
  it('moves focus to a new result', () => {
    const props = {
      file,
      schema: sampleSchemaBfi,
      columns,
      status: { kind: 'idle' } as LoadStatus,
      onRun: vi.fn(),
      onBack: vi.fn(),
    }
    const { rerender } = render(<Robustness {...props} result={null} />)
    rerender(
      <Robustness
        {...props}
        result={{ analysis: robustnessGender.robustness.analysis, response: robustnessGender }}
      />,
    )
    expect(screen.getByRole('heading', { name: 'Result' })).toHaveFocus()
  })
})

describe('Robustness table numbers', () => {
  it('writes Mann–Whitney U with thousands separators', () => {
    render(
      <Robustness
        file={file}
        schema={sampleSchemaBfi}
        columns={columns}
        result={{ analysis: robustnessGender.robustness.analysis, response: robustnessGender }}
        status={{ kind: 'idle' }}
        onRun={vi.fn()}
        onBack={vi.fn()}
      />,
    )
    const rows = within(screen.getByRole('table')).getAllByRole('row')
    expect(rows[1]).toHaveTextContent('637,036')
    expect(rows[4]).toHaveTextContent('519,211.5')
  })
})
