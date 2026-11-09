import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { analyzeBfi } from '../test/fixtures'
import { FlagTable } from './FlagTable'

const { flagged, n_flagged } = analyzeBfi.careless

const bodyRows = () => within(screen.getByRole('table')).getAllByRole('row').slice(1)
const firstCells = () => bodyRows().map((row) => within(row).getByRole('rowheader').textContent)
const header = (name: string) => screen.getByRole('button', { name: new RegExp(`^${name}`) })

describe('FlagTable', () => {
  it('starts in the API order and shows 25 rows', () => {
    render(<FlagTable rows={flagged} nFlagged={n_flagged} />)
    expect(bodyRows()).toHaveLength(25)
    expect(firstCells()[0]).toBe(flagged[0].respondent)
    expect(
      screen.getByText(/The 200 ranked highest of 686 flagged respondents/),
    ).toBeInTheDocument()
  })

  it('shows the reasons for each flag', () => {
    render(<FlagTable rows={flagged} nFlagged={n_flagged} />)
    const first = bodyRows()[0]
    expect(first).toHaveTextContent(flagged[0].reasons)
    expect(first).toHaveTextContent(String(flagged[0].csv_row))
  })

  it('sorts by a column and marks it with aria-sort', () => {
    render(<FlagTable rows={flagged} nFlagged={n_flagged} />)
    fireEvent.click(header('CSV row'))
    const th = header('CSV row').closest('th')!
    expect(th).toHaveAttribute('aria-sort', 'descending')
    const max = Math.max(...flagged.map((r) => r.csv_row))
    expect(bodyRows()[0]).toHaveTextContent(String(max))

    fireEvent.click(header('CSV row'))
    expect(th).toHaveAttribute('aria-sort', 'ascending')
    const min = Math.min(...flagged.map((r) => r.csv_row))
    expect(within(bodyRows()[0]).getAllByRole('cell')[0]).toHaveTextContent(String(min))
  })

  it('sorts respondent IDs as numbers, not as text', () => {
    const rows = [
      { ...flagged[0], respondent: '100', csv_row: 3 },
      { ...flagged[0], respondent: '9', csv_row: 2 },
      { ...flagged[0], respondent: '20', csv_row: 4 },
    ]
    render(<FlagTable rows={rows} nFlagged={3} />)
    fireEvent.click(header('Respondent'))
    expect(firstCells()).toEqual(['9', '20', '100'])
  })

  it('puts missing composite scores last', () => {
    const rows = [
      { ...flagged[0], composite: null, csv_row: 2, respondent: 'a' },
      { ...flagged[0], composite: 0.5, csv_row: 3, respondent: 'b' },
      { ...flagged[0], composite: 0.9, csv_row: 4, respondent: 'c' },
    ]
    render(<FlagTable rows={rows} nFlagged={3} />)
    fireEvent.click(header('Composite'))
    expect(firstCells()).toEqual(['c', 'b', 'a'])
    expect(bodyRows()[2]).toHaveTextContent('—')
  })

  it('shows all rows on request', () => {
    render(<FlagTable rows={flagged} nFlagged={n_flagged} />)
    fireEvent.click(screen.getByRole('button', { name: 'Show all 200' }))
    expect(bodyRows()).toHaveLength(200)
  })

  it('says when nobody was flagged', () => {
    render(<FlagTable rows={[]} nFlagged={0} />)
    expect(screen.getByText('No respondent was flagged by any rule.')).toBeInTheDocument()
  })
})
