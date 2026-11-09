import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { analyzeBfi, robustnessGender, sampleSchemaBfi } from '../test/fixtures'
import { Results } from './Results'

const file = new File(['id,A1\n'], 'bfi.csv', { type: 'text/csv' })

function setup(robustness: Parameters<typeof Results>[0]['robustness'] = null) {
  const onChangeScales = vi.fn()
  const onCheckRobustness = vi.fn()
  render(
    <Results
      results={analyzeBfi}
      robustness={robustness}
      file={file}
      schema={sampleSchemaBfi}
      onChangeScales={onChangeScales}
      onCheckRobustness={onCheckRobustness}
    />,
  )
  return { onChangeScales, onCheckRobustness }
}

describe('Results', () => {
  it('puts the verdict from the API first', () => {
    setup()
    const heading = screen.getByRole('heading', { level: 1 })
    expect(heading).toHaveTextContent('Review before drawing conclusions')
    expect(
      screen.getByText(
        'Look at careless responding and reliability before drawing conclusions. Not checked: robustness.',
      ),
    ).toBeInTheDocument()
  })

  it('shows one chip per check, with a word and not only a colour', () => {
    setup()
    const list = screen.getByRole('list', { name: 'Checks' })
    const chips = within(list).getAllByRole('listitem')
    expect(chips.map((c) => c.textContent)).toEqual([
      '⚠Careless respondingReview',
      '⚠ReliabilityReview',
      '✓Factor structureNo concern',
      'RobustnessNot checked',
    ])
    expect(within(list).getByRole('link', { name: /Careless responding/ })).toHaveAttribute(
      'href',
      '#careless',
    )
    expect(within(list).getByRole('link', { name: /Robustness/ })).toHaveAttribute(
      'href',
      '#robustness',
    )
  })

  it('offers the robustness check while it has not been run', () => {
    const { onCheckRobustness } = setup()
    const section = document.getElementById('robustness')!
    expect(section).toHaveTextContent('Not checked yet.')
    fireEvent.click(within(section).getByRole('button', { name: 'Check robustness' }))
    expect(onCheckRobustness).toHaveBeenCalled()
  })

  it('uses the verdict band from the robustness check once it has run', () => {
    setup({ analysis: robustnessGender.robustness.analysis, response: robustnessGender })
    const chips = within(screen.getByRole('list', { name: 'Checks' })).getAllByRole('listitem')
    expect(chips[3]).toHaveTextContent('RobustnessNo concern')
    // The robustness response's own sentence no longer lists robustness as not checked.
    expect(
      screen.getByText('Look at careless responding and reliability before drawing conclusions.'),
    ).toBeInTheDocument()
    const section = document.getElementById('robustness')!
    expect(section).toHaveTextContent(/^Robustnesss*✓s*No concern/)
    expect(section).toHaveTextContent(robustnessGender.robustness.sentence)
  })

  it('offers the three downloads', () => {
    setup()
    const section = document.getElementById('downloads')!
    for (const name of ['Download report', 'Download flags (CSV)', 'Download schema (JSON)']) {
      expect(within(section).getByRole('button', { name })).toBeEnabled()
    }
  })

  it('shows the key figures', () => {
    setup()
    const figure = (label: string) => screen.getByText(label).nextElementSibling
    expect(figure('Respondents')).toHaveTextContent('2,800')
    expect(figure('Flagged by 1+ rule')).toHaveTextContent('686')
    expect(figure('Flagged by 2+ rules')).toHaveTextContent('72')
  })

  it('lists the rules, including the ones that were not applied', () => {
    setup()
    const rules = screen.getByRole('table', { name: /Rules used to flag respondents/ })
    expect(within(rules).getByRole('row', { name: /Even-odd consistency/ })).toHaveTextContent(
      '490',
    )
    expect(within(rules).getByRole('row', { name: /Seconds per item/ })).toHaveTextContent(
      'not applied (no completion-time column)',
    )
  })

  it('shows alpha and omega per scale', () => {
    setup()
    const table = screen.getByRole('table', { name: /Reliability of each scale/ })
    expect(within(table).getByRole('row', { name: /^Agreeableness/ })).toHaveTextContent(
      /5\s*2,709\s*0\.70\s*0\.69 to 0\.72\s*0\.72/,
    )
  })

  it('marks cross-loading questions with a word', () => {
    setup()
    const loadings = screen.getByRole('table', { name: 'Factor loadings' })
    expect(within(loadings).getByRole('row', { name: /^E3/ })).toHaveTextContent('cross (F5)')
    expect(within(loadings).getByRole('row', { name: /^A1/ })).not.toHaveTextContent(/weak|cross/)
    // Column headings name the scale aligned with each factor.
    expect(within(loadings).getByRole('columnheader', { name: /F4\s*Agreeableness/ }))
  })

  it('offers the charts as tables', () => {
    setup()
    const toggles = screen.getAllByRole('button', { name: 'Show as table' })
    expect(toggles).toHaveLength(2)
    fireEvent.click(toggles[1])
    const scree = screen.getByRole('table', {
      name: 'Observed eigenvalues and random-data threshold',
    })
    expect(within(scree).getAllByRole('row')).toHaveLength(26)
    expect(within(scree).getAllByRole('row')[1]).toHaveTextContent(/1\s*5\.13\s*1\.22/)
  })

  it('shows the sample-size results as information', () => {
    setup()
    const section = document.getElementById('sample-size')!
    expect(within(section).getByRole('row', { name: /Two groups/ })).toHaveTextContent('d = 0.11')
    expect(within(section).getByRole('row', { name: /3 groups/ })).toHaveTextContent('f = 0.06')
  })

  it('lists data checks and limitations', () => {
    setup()
    expect(screen.getByText("16 blank or NA answer(s) in 'A1'.")).toBeInTheDocument()
    expect(screen.getByText(/Statistical checks cannot fix who was sampled/)).toBeInTheDocument()
  })

  it('goes back to change the scales', () => {
    const { onChangeScales } = setup()
    fireEvent.click(screen.getByRole('button', { name: 'Change scales' }))
    expect(onChangeScales).toHaveBeenCalled()
  })
})
