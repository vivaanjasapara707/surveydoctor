import { useState } from 'react'
import type { FlaggedRespondent } from '../api/client'
import { formatCount, formatNumber } from '../lib/format'
import { TABLE } from '../lib/status'
import { Button } from './Button'

type SortKey = 'respondent' | 'csv_row' | 'n_rules' | 'composite'
type Direction = 'ascending' | 'descending'

const COLUMNS: { key: SortKey; label: string; numeric: boolean }[] = [
  { key: 'respondent', label: 'Respondent', numeric: false },
  { key: 'csv_row', label: 'CSV row', numeric: true },
  { key: 'n_rules', label: 'Rules', numeric: true },
  { key: 'composite', label: 'Composite', numeric: true },
]

const collator = new Intl.Collator('en-GB', { numeric: true })

function compare(a: FlaggedRespondent, b: FlaggedRespondent, key: SortKey): number {
  if (key === 'respondent') return collator.compare(a.respondent, b.respondent)
  // Missing composite scores sort last in both directions' natural order.
  const x = a[key] ?? Number.NEGATIVE_INFINITY
  const y = b[key] ?? Number.NEGATIVE_INFINITY
  return x - y
}

interface FlagTableProps {
  rows: FlaggedRespondent[]
  /** Respondents flagged in total; the API sends the top 200. */
  nFlagged: number
  /** Rows shown before "Show all". */
  pageSize?: number
}

/** Flagged respondents with the reasons for each flag (BLUEPRINT §7.12). Sortable by any
 *  column; the API's order (most rules first, then highest composite) is the default. */
export function FlagTable({ rows, nFlagged, pageSize = 25 }: FlagTableProps) {
  const [sort, setSort] = useState<{ key: SortKey; direction: Direction } | null>(null)
  const [showAll, setShowAll] = useState(false)

  const sorted = sort
    ? [...rows].sort((a, b) => {
        const order = compare(a, b, sort.key)
        return sort.direction === 'ascending' ? order : -order
      })
    : rows
  const visible = showAll ? sorted : sorted.slice(0, pageSize)

  const toggle = (key: SortKey) => {
    if (sort?.key === key) {
      setSort({ key, direction: sort.direction === 'ascending' ? 'descending' : 'ascending' })
    } else {
      // Numbers start with the largest (most suspicious) first; IDs start from A.
      setSort({ key, direction: key === 'respondent' ? 'ascending' : 'descending' })
    }
  }

  if (rows.length === 0) {
    return <p className="text-graphite">No respondent was flagged by any rule.</p>
  }

  return (
    <div className="space-y-2">
      <h3 className="font-semibold">Flagged respondents</h3>
      {/* Outside the table, so it wraps on a phone instead of scrolling with the table. */}
      <p className="text-table text-graphite">
        {rows.length < nFlagged
          ? `The ${formatCount(rows.length)} ranked highest of ${formatCount(nFlagged)} flagged respondents. `
          : `All ${formatCount(nFlagged)} flagged respondents. `}
        Select a column heading to sort.
      </p>
      <div className={TABLE.box} role="region" aria-label="Flagged respondents" tabIndex={0}>
        <table className={TABLE.table}>
          <caption className="sr-only">Flagged respondents</caption>
          <thead className={TABLE.head}>
            <tr>
              {COLUMNS.map((column) => {
                const active = sort?.key === column.key
                return (
                  <th
                    key={column.key}
                    scope="col"
                    aria-sort={active ? sort.direction : undefined}
                    className={column.numeric ? TABLE.thNum : TABLE.th}
                  >
                    <button
                      type="button"
                      onClick={() => toggle(column.key)}
                      className="inline-flex min-h-8 items-center gap-1 rounded-sm font-semibold text-graphite hover:text-ink"
                    >
                      {column.label}
                      <span aria-hidden="true" className={active ? 'text-ink' : 'text-rule'}>
                        {active && sort.direction === 'ascending' ? '↑' : '↓'}
                      </span>
                    </button>
                  </th>
                )
              })}
              <th scope="col" className={TABLE.th}>
                Reasons
              </th>
            </tr>
          </thead>
          <tbody>
            {visible.map((row) => (
              <tr key={row.csv_row}>
                <th scope="row" className={`${TABLE.td} font-normal whitespace-nowrap`}>
                  {row.respondent}
                </th>
                <td className={TABLE.tdNum}>{row.csv_row}</td>
                <td className={TABLE.tdNum}>{row.n_rules}</td>
                <td className={TABLE.tdNum}>{formatNumber(row.composite)}</td>
                <td className={`${TABLE.td} min-w-72`}>{row.reasons}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {sorted.length > pageSize && (
        <Button variant="text" onClick={() => setShowAll(!showAll)}>
          {showAll ? `Show the first ${pageSize}` : `Show all ${formatCount(sorted.length)}`}
        </Button>
      )}
    </div>
  )
}
