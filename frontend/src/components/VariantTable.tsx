import type { RobustnessResponse } from '../api/client'
import { formatCount, formatLarge, formatNumber, formatP, pText } from '../lib/format'
import { TABLE } from '../lib/status'

type Robustness = RobustnessResponse['robustness']

const DIRECTION: Record<string, string> = {
  positive: 'positive',
  negative: 'negative',
  none: 'none',
}

/** The declared analysis on all respondents and without each flag variant (BLUEPRINT §7.6).
 *  A variant that changed the result gets a tint and the word "changed", never the tint
 *  alone (design.md §6). */
export function VariantTable({ robustness }: { robustness: Robustness }) {
  const groups = robustness.analysis.type === 'group_comparison'
  // For a correlation the effect size is r itself, the estimate, so it is not repeated.
  const showEffect = groups
  return (
    <div className={TABLE.box} role="region" aria-label="Robustness variants" tabIndex={0}>
      <table className={TABLE.table}>
        <caption className="sr-only">
          {robustness.estimate_label} on all respondents and without each group of flagged
          respondents
        </caption>
        <thead className={TABLE.head}>
          <tr>
            <th scope="col" className={TABLE.th}>
              Respondents used
            </th>
            <th scope="col" className={TABLE.thNum}>
              N
            </th>
            <th scope="col" className={TABLE.thNum}>
              {robustness.estimate_label}
            </th>
            <th scope="col" className={TABLE.thNum}>
              95% CI
            </th>
            <th scope="col" className={TABLE.thNum}>
              p
            </th>
            <th scope="col" className={TABLE.th}>
              Significant
            </th>
            <th scope="col" className={TABLE.th}>
              Direction
            </th>
            {showEffect && (
              <th scope="col" className={TABLE.thNum}>
                {robustness.effect_label}
              </th>
            )}
            <th scope="col" className={TABLE.thNum}>
              {robustness.companion_label}
            </th>
          </tr>
        </thead>
        <tbody>
          {robustness.variants.map((v) => (
            <tr key={v.variant} className={v.changed ? 'bg-review-tint' : undefined}>
              <th scope="row" className={`${TABLE.td} min-w-56 font-normal`}>
                {v.label}
                {v.n_excluded > 0 && (
                  <span className="block text-small text-graphite">
                    {formatCount(v.n_excluded)} left out
                  </span>
                )}
                {v.changed && <span className="block font-semibold text-review">⚠ changed</span>}
                {v.note && <span className="block text-small text-graphite">{v.note}</span>}
              </th>
              <td className={TABLE.tdNum}>
                {formatCount(v.n)}
                {groups && v.n_a !== null && v.n_b !== null && (
                  <span className="block text-small text-graphite">
                    A {formatCount(v.n_a)} · B {formatCount(v.n_b)}
                  </span>
                )}
              </td>
              <td className={TABLE.tdNum}>{formatNumber(v.estimate)}</td>
              <td className={TABLE.tdNum}>
                {formatNumber(v.ci_low)} to {formatNumber(v.ci_high)}
              </td>
              <td className={TABLE.tdNum}>{formatP(v.p)}</td>
              <td className={TABLE.td}>
                {v.significant === null ? '—' : v.significant ? 'yes' : 'no'}
              </td>
              <td className={TABLE.td}>{v.direction ? DIRECTION[v.direction] : '—'}</td>
              {showEffect && <td className={TABLE.tdNum}>{formatNumber(v.effect_size)}</td>}
              <td className={TABLE.tdNum}>
                {groups ? formatLarge(v.companion) : formatNumber(v.companion)}
                <span className="block text-small text-graphite">{pText(v.companion_p)}</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
