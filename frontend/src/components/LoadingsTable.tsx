import type { StructureResult } from '../api/client'
import { formatNumber } from '../lib/format'
import { TABLE } from '../lib/status'

type EFA = NonNullable<StructureResult['efa']>

interface LoadingsTableProps {
  efa: EFA
  /** Factor -> scale names whose questions mostly load on it, for the column headings. */
  factorScales: Record<string, string[]>
}

/** EFA loadings: one row per question, the main loading in bold, and weak or cross-loading
 *  questions marked with a tint and a word, never the tint alone (design.md §6). */
export function LoadingsTable({ efa, factorScales }: LoadingsTableProps) {
  return (
    <div className="space-y-2">
      <h3 className="font-semibold">Factor loadings</h3>
      {/* Outside the table, so it wraps on a phone instead of scrolling with the table.
          Thresholds as in backend/surveydoctor/structure.py (WEAK_LOADING, CROSS_LOADING). */}
      <p className="text-table text-graphite">
        Loadings of each question on each factor; the main loading is in bold. Weak: main loading
        below 0.30 in size. Cross: also 0.30 or more on a second factor.
      </p>
      <div className={TABLE.box} role="region" aria-label="Factor loadings" tabIndex={0}>
        <table className={TABLE.table}>
          <caption className="sr-only">Factor loadings</caption>
          <thead className={TABLE.head}>
            <tr>
              <th scope="col" className={TABLE.th}>
                Question
              </th>
              {efa.factors.map((factor) => (
                <th key={factor} scope="col" className={TABLE.thNum}>
                  {factor}
                  {factorScales[factor]?.length ? (
                    <span className="block text-small font-normal">
                      {factorScales[factor].join(', ')}
                    </span>
                  ) : null}
                </th>
              ))}
              <th scope="col" className={TABLE.thNum}>
                Communality
              </th>
              <th scope="col" className={TABLE.th}>
                Note
              </th>
            </tr>
          </thead>
          <tbody>
            {efa.items.map((item) => {
              const marked = item.weak || item.cross_loading
              return (
                <tr key={item.item} className={marked ? 'bg-review-tint' : undefined}>
                  <th scope="row" className={`${TABLE.td} font-mono font-normal`}>
                    {item.item}
                  </th>
                  {efa.factors.map((factor) => (
                    <td
                      key={factor}
                      className={`${TABLE.tdNum} ${factor === item.primary_factor ? 'font-semibold' : 'text-graphite'}`}
                    >
                      {formatNumber(item.loadings[factor])}
                    </td>
                  ))}
                  <td className={TABLE.tdNum}>{formatNumber(item.communality)}</td>
                  <td className={`${TABLE.td} whitespace-nowrap`}>
                    {item.weak && <span className="font-semibold text-review">⚠ weak</span>}
                    {item.weak && item.cross_loading && ', '}
                    {item.cross_loading && (
                      <span className="font-semibold text-review">
                        {!item.weak && '⚠ '}cross ({item.second_factor})
                      </span>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
