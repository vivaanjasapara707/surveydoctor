import type { ReactNode } from 'react'
import type {
  Analysis,
  AnalyzeResponse,
  CheckStatus,
  RobustnessResponse,
  SensitivityResult,
  SurveySchema,
} from '../api/client'
import { Button } from '../components/Button'
import { Downloads } from '../components/Downloads'
import { FlagTable } from '../components/FlagTable'
import { KeyFigures } from '../components/KeyFigures'
import { LoadingsTable } from '../components/LoadingsTable'
import { Notice } from '../components/Notice'
import { ScoreHistogram } from '../components/ScoreHistogram'
import { ScreePlot } from '../components/ScreePlot'
import { StatusTag } from '../components/StatusTag'
import { VerdictBand } from '../components/VerdictBand'
import { formatCount, formatNumber, pText } from '../lib/format'
import { TABLE } from '../lib/status'

const SECTIONS = [
  { id: 'careless', label: 'Careless responding' },
  { id: 'reliability', label: 'Reliability' },
  { id: 'structure', label: 'Structure' },
  { id: 'sample-size', label: 'Sample size' },
  { id: 'robustness', label: 'Robustness' },
  { id: 'data-checks', label: 'Data checks' },
  { id: 'limitations', label: 'Limitations' },
  { id: 'downloads', label: 'Downloads' },
]

/** Verdict checks and the section on this screen that each chip jumps to. */
const CHECK_SECTIONS: Record<string, string> = {
  careless: 'careless',
  reliability: 'reliability',
  structure: 'structure',
  robustness: 'robustness',
}

interface ResultsProps {
  results: AnalyzeResponse
  /** The robustness check, once run; its verdict band replaces the one from /api/analyze. */
  robustness: { analysis: Analysis; response: RobustnessResponse } | null
  file: File
  schema: SurveySchema
  onChangeScales: () => void
  onCheckRobustness: () => void
}

/** Results: the verdict first, then the evidence in the order a careful reader checks it
 *  (BLUEPRINT §7.12 screen 5, design.md §1). Every number and sentence comes from the API. */
export function Results({
  results,
  robustness,
  file,
  schema,
  onChangeScales,
  onCheckRobustness,
}: ResultsProps) {
  const { overview, careless, reliability, structure, sensitivity } = results
  const verdict = robustness?.response.verdict ?? results.verdict
  const check = (id: string) => verdict.checks.find((c) => c.check === id)

  return (
    <div className="space-y-10">
      <div className="space-y-6">
        <VerdictBand verdict={verdict} sections={CHECK_SECTIONS} />
        <KeyFigures
          figures={[
            { label: 'Respondents', value: formatCount(overview.n_respondents) },
            { label: 'Questions', value: formatCount(overview.n_items) },
            { label: 'Flagged by 1+ rule', value: formatCount(overview.n_flagged) },
            { label: 'Flagged by 2+ rules', value: formatCount(overview.n_flagged_two_rules) },
          ]}
        />
      </div>

      <nav aria-label="Sections" className="border-y border-rule py-2">
        <ul className="flex flex-col gap-x-4 sm:flex-row sm:flex-wrap">
          {SECTIONS.map((section) => (
            <li key={section.id}>
              <a
                href={`#${section.id}`}
                className="inline-flex min-h-10 items-center rounded-sm text-signal underline underline-offset-2 hover:text-ink pointer-coarse:min-h-11"
              >
                {section.label}
              </a>
            </li>
          ))}
        </ul>
      </nav>

      <Section id="careless" title="Careless responding" status={check('careless')}>
        <p>{careless.sentence}</p>
        <div className={TABLE.box}>
          <table className={TABLE.table}>
            <caption className="px-3 py-2 text-left text-table text-graphite">
              Rules used to flag respondents
            </caption>
            <thead className={TABLE.head}>
              <tr>
                <th scope="col" className={TABLE.th}>
                  Rule
                </th>
                <th scope="col" className={TABLE.th}>
                  Flags a respondent when
                </th>
                <th scope="col" className={TABLE.thNum}>
                  Flagged
                </th>
              </tr>
            </thead>
            <tbody>
              {careless.rules.map((rule) => (
                <tr key={rule.name}>
                  <th scope="row" className={`${TABLE.td} font-normal`}>
                    {rule.label}
                  </th>
                  <td className={TABLE.td}>{rule.description}</td>
                  <td className={TABLE.tdNum}>
                    {rule.count !== null ? (
                      formatCount(rule.count)
                    ) : (
                      <span className="whitespace-normal text-slate">{rule.status}</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <ScoreHistogram
          histogram={careless.histogram}
          n={overview.n_respondents}
          note={careless.composite_note}
        />
        <FlagTable rows={careless.flagged} nFlagged={careless.n_flagged} />
        <p className="text-table text-graphite">
          The flags file under{' '}
          <a href="#downloads" className="text-signal underline">
            Downloads
          </a>{' '}
          lists every respondent with all indices and reasons.
        </p>
        <Notice kind="note" title="Flags are reasons to look, not proof">
          <p>{careless.heuristics_note}</p>
        </Notice>
      </Section>

      <Section id="reliability" title="Reliability" status={check('reliability')}>
        <p className="text-table text-graphite">
          N is the number of respondents who answered every question of the scale.
        </p>
        <div className={TABLE.box}>
          <table className={TABLE.table}>
            <caption className="px-3 py-2 text-left text-table text-graphite">
              Reliability of each scale
            </caption>
            <thead className={TABLE.head}>
              <tr>
                <th scope="col" className={TABLE.th}>
                  Scale
                </th>
                <th scope="col" className={TABLE.thNum}>
                  Questions
                </th>
                <th scope="col" className={TABLE.thNum}>
                  N
                </th>
                <th scope="col" className={TABLE.thNum}>
                  Alpha
                </th>
                <th scope="col" className={TABLE.thNum}>
                  95% CI
                </th>
                <th scope="col" className={TABLE.thNum}>
                  Omega
                </th>
              </tr>
            </thead>
            <tbody>
              {reliability.map((scale) => (
                <tr key={scale.scale}>
                  <th scope="row" className={`${TABLE.td} font-normal`}>
                    {scale.scale}
                  </th>
                  <td className={TABLE.tdNum}>{scale.n_items}</td>
                  <td className={TABLE.tdNum}>{formatCount(scale.n_used)}</td>
                  <td className={TABLE.tdNum}>{formatNumber(scale.alpha)}</td>
                  <td className={TABLE.tdNum}>
                    {formatNumber(scale.alpha_ci_low)} to {formatNumber(scale.alpha_ci_high)}
                  </td>
                  <td className={TABLE.tdNum}>{formatNumber(scale.omega_total)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {reliability.flatMap((scale) =>
          scale.reverse_warnings.map((warning) => (
            <Notice
              key={`${scale.scale}-${warning.item}`}
              kind="review"
              title={`${scale.scale}: check ${warning.item}`}
            >
              <p>{warning.message}</p>
            </Notice>
          )),
        )}
        <div className="space-y-2">
          {reliability.map((scale) => (
            <details key={scale.scale} className="rounded-sm border border-rule">
              <summary className="cursor-pointer px-3 py-2 font-semibold">
                {scale.scale}: details
              </summary>
              <div className="space-y-3 border-t border-rule px-3 py-3">
                <p>{scale.sentence}</p>
                <div className={TABLE.box}>
                  <table className={TABLE.table}>
                    <thead className={TABLE.head}>
                      <tr>
                        <th scope="col" className={TABLE.th}>
                          Question
                        </th>
                        <th scope="col" className={TABLE.thNum}>
                          Corrected item-total r
                        </th>
                        <th scope="col" className={TABLE.thNum}>
                          Alpha if deleted
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {scale.item_stats.map((item) => (
                        <tr key={item.item}>
                          <th scope="row" className={`${TABLE.td} font-mono font-normal`}>
                            {item.item}
                          </th>
                          <td className={TABLE.tdNum}>{formatNumber(item.corrected_item_total)}</td>
                          <td className={TABLE.tdNum}>{formatNumber(item.alpha_if_deleted)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {scale.n_excluded > 0 && (
                  <p className="text-table text-graphite">
                    {formatCount(scale.n_excluded)} respondents with a missing answer in this scale
                    were left out.
                  </p>
                )}
              </div>
            </details>
          ))}
        </div>
      </Section>

      <Section id="structure" title="Factor structure" status={check('structure')}>
        <p>{structure.sentence}</p>
        {structure.skipped_reason ? (
          <Notice kind="review" title="Factor analysis was not run">
            <p>{structure.skipped_reason}</p>
          </Notice>
        ) : (
          <>
            <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-table sm:grid-cols-4">
              <Figure label="KMO" value={formatNumber(structure.kmo?.overall)} />
              <Figure
                label="Bartlett's test"
                value={
                  structure.bartlett
                    ? `χ²(${structure.bartlett.df}) = ${formatNumber(structure.bartlett.chi_square, 0)}, ${pText(structure.bartlett.p_value)}`
                    : '—'
                }
              />
              <Figure
                label="Factors used"
                value={`${structure.n_factors ?? '—'} (${structure.n_factors_source})`}
              />
              <Figure label="Respondents used" value={formatCount(structure.n_used)} />
            </dl>
            {structure.parallel && <ScreePlot parallel={structure.parallel} />}
            {structure.efa && (
              <LoadingsTable efa={structure.efa} factorScales={factorScales(results)} />
            )}
            {structure.alignment.length > 0 && <Alignment results={results} />}
            {structure.n_excluded > 0 && (
              <p className="text-table text-graphite">
                {formatCount(structure.n_excluded)} respondents with at least one missing answer
                were left out of the factor analysis.
              </p>
            )}
          </>
        )}
      </Section>

      <Section id="sample-size" title="Sample size">
        <p className="text-graphite">
          The smallest effect this sample can detect with 80% power. Shown for information; it is
          not a pass or fail.
        </p>
        <div className={TABLE.box}>
          <table className={TABLE.table}>
            <thead className={TABLE.head}>
              <tr>
                <th scope="col" className={TABLE.th}>
                  Analysis
                </th>
                <th scope="col" className={TABLE.thNum}>
                  Smallest detectable effect
                </th>
                <th scope="col" className={TABLE.th}>
                  Cohen's label
                </th>
              </tr>
            </thead>
            <tbody>
              {sensitivity.map((s) => (
                <tr key={s.test}>
                  <th scope="row" className={`${TABLE.td} font-normal`}>
                    {sensitivityName(s)}
                  </th>
                  <td className={TABLE.tdNum}>
                    {s.effect_measure} = {formatNumber(s.min_effect)}
                  </td>
                  <td className={TABLE.td}>{s.label}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <ul className="list-disc space-y-1 pl-5">
          {sensitivity.map((s) => (
            <li key={s.test}>{s.sentence}</li>
          ))}
        </ul>
        {sensitivity[0] && <p className="text-table text-graphite">{sensitivity[0].caveat}</p>}
      </Section>

      <Section id="robustness" title="Robustness" status={check('robustness')}>
        {robustness ? (
          <>
            <p>{robustness.response.robustness.sentence}</p>
            <Button onClick={onCheckRobustness}>See the variant table</Button>
          </>
        ) : (
          <>
            <p className="max-w-measure">
              Not checked yet. Choose the main result you plan to report, and SurveyDoctor checks
              whether it still holds without the flagged respondents.
            </p>
            <Button variant="primary" onClick={onCheckRobustness}>
              Check robustness
            </Button>
          </>
        )}
      </Section>

      <Section id="data-checks" title="Data checks">
        {results.issues.length === 0 ? (
          <p>No blank, invalid or removed answers were found.</p>
        ) : (
          <div className={TABLE.box}>
            <table className={TABLE.table}>
              <caption className="px-3 py-2 text-left text-table text-graphite">
                What was found while reading the answers
              </caption>
              <thead className={TABLE.head}>
                <tr>
                  <th scope="col" className={TABLE.th}>
                    Column
                  </th>
                  <th scope="col" className={TABLE.th}>
                    Finding
                  </th>
                </tr>
              </thead>
              <tbody>
                {results.issues.map((issue, i) => (
                  <tr key={i}>
                    <th scope="row" className={`${TABLE.td} font-mono font-normal`}>
                      {issue.column ?? '—'}
                    </th>
                    <td className={TABLE.td}>
                      {issue.message}
                      {issue.examples.length > 0 && (
                        <span className="text-graphite">
                          {' '}
                          Examples: {issue.examples.join(', ')}.
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {results.warnings.length > 0 && (
          <details className="rounded-sm border border-rule">
            <summary className="cursor-pointer px-3 py-2 font-semibold">
              Notes from the checks ({results.warnings.length})
            </summary>
            <ul className="list-disc space-y-1 border-t border-rule py-3 pr-3 pl-8">
              {results.warnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          </details>
        )}
      </Section>

      <Section id="limitations" title="Limitations">
        <ul className="list-disc space-y-1 pl-5">
          {results.limitations.map((limitation) => (
            <li key={limitation}>{limitation}</li>
          ))}
        </ul>
      </Section>

      <Section id="downloads" title="Downloads">
        <Downloads file={file} schema={schema} analysis={robustness?.analysis ?? null} />
      </Section>

      <div className="flex flex-wrap gap-3">
        <Button onClick={onChangeScales}>Change scales</Button>
      </div>
    </div>
  )
}

function sensitivityName(s: SensitivityResult): string {
  if (s.test === 'two_groups') return 'Two groups (t-test)'
  if (s.test === 'correlation') return 'Correlation'
  if (s.test === 'anova') return `${s.details.k_groups ?? 'Several'} groups (one-way ANOVA)`
  return s.test
}

function Section({
  id,
  title,
  status,
  children,
}: {
  id: string
  title: string
  status?: CheckStatus
  children: ReactNode
}) {
  return (
    <section id={id} aria-labelledby={`${id}-heading`} className="scroll-mt-4 space-y-4">
      <div className="border-b border-rule pb-2">
        <h2 id={`${id}-heading`} className="text-section font-semibold">
          {title}
        </h2>
        {status && (
          <p className="mt-1">
            <StatusTag status={status.status} />
            <span className="text-graphite"> · {status.reason}</span>
          </p>
        )}
      </div>
      {children}
    </section>
  )
}

function Figure({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-graphite">{label}</dt>
      <dd className="font-semibold tabular-nums">{value}</dd>
    </div>
  )
}

/** Factor -> names of the scales the API aligned with it (for the loadings headings). */
function factorScales(results: AnalyzeResponse): Record<string, string[]> {
  const map: Record<string, string[]> = {}
  for (const a of results.structure.alignment) (map[a.factor] ??= []).push(a.scale)
  return map
}

function Alignment({ results }: { results: AnalyzeResponse }) {
  return (
    <div className={TABLE.box}>
      <table className={TABLE.table}>
        <caption className="px-3 py-2 text-left text-table text-graphite">
          Do the scales you declared match the factors?
        </caption>
        <thead className={TABLE.head}>
          <tr>
            <th scope="col" className={TABLE.th}>
              Scale
            </th>
            <th scope="col" className={TABLE.th}>
              Main factor
            </th>
            <th scope="col" className={TABLE.thNum}>
              Questions on it
            </th>
            <th scope="col" className={TABLE.th}>
              Shares the factor with
            </th>
          </tr>
        </thead>
        <tbody>
          {results.structure.alignment.map((a) => (
            <tr key={a.scale} className={a.shared_with.length > 0 ? 'bg-review-tint' : undefined}>
              <th scope="row" className={`${TABLE.td} font-normal`}>
                {a.scale}
              </th>
              <td className={TABLE.td}>{a.factor}</td>
              <td className={TABLE.tdNum}>
                {a.n_matching} of {a.items.length}
              </td>
              <td className={TABLE.td}>
                {a.shared_with.length > 0 ? (
                  <span className="font-semibold text-review">⚠ {a.shared_with.join(', ')}</span>
                ) : (
                  <span className="text-slate">no other scale</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
