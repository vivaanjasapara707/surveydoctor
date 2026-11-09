import { useEffect, useId, useRef, useState } from 'react'
import {
  WAKE_UP_MESSAGE,
  type Analysis,
  type RobustnessResponse,
  type SurveySchema,
} from '../api/client'
import { Button } from '../components/Button'
import { Downloads } from '../components/Downloads'
import { Notice } from '../components/Notice'
import { StatusTag } from '../components/StatusTag'
import { VariantTable } from '../components/VariantTable'
import {
  groupColumns,
  initialAnalysisDraft,
  validateAnalysis,
  valuesListed,
  type AnalysisDraft,
} from '../lib/robustness'
import type { ColumnChoice } from '../lib/scales'
import type { LoadStatus } from '../lib/upload'

interface RobustnessProps {
  file: File
  schema: SurveySchema
  columns: ColumnChoice[]
  /** The last check run, if any. */
  result: { analysis: Analysis; response: RobustnessResponse } | null
  status: LoadStatus
  onRun: (analysis: Analysis) => void
  onBack: () => void
}

const control =
  'mt-1 min-h-10 max-w-full rounded-sm border border-field bg-paper px-3 pointer-coarse:min-h-11'
const field = `${control} w-72`

/** Robustness (BLUEPRINT §7.12 screen 6): declare the main result you plan to report, and
 *  see whether it holds without the flagged respondents. */
export function Robustness({
  file,
  schema,
  columns,
  result,
  status,
  onRun,
  onBack,
}: RobustnessProps) {
  const candidates = groupColumns(columns, schema)
  const scales = Object.keys(schema.scales)
  const canGroup = candidates.length > 0
  const canCorrelate = scales.length >= 2
  const [draft, setDraft] = useState<AnalysisDraft>(() =>
    initialAnalysisDraft(schema, canGroup, result?.analysis ?? null),
  )
  const [errors, setErrors] = useState<string[]>([])
  const errorRef = useRef<HTMLDivElement>(null)
  const resultRef = useRef<HTMLHeadingElement>(null)
  // The result shown when the screen opened; a different one is new and gets attention.
  const shownResult = useRef(result)

  // A new result appears below the form, out of sight on most screens: bring it into view
  // and move keyboard focus to it.
  useEffect(() => {
    if (!result || result === shownResult.current) return
    shownResult.current = result
    resultRef.current?.focus()
    resultRef.current?.scrollIntoView?.({ block: 'start' })
  }, [result])
  const ids = {
    scale: useId(),
    column: useId(),
    a: useId(),
    b: useId(),
    x: useId(),
    y: useId(),
  }
  const running = status.kind === 'loading'
  const column = candidates.find((c) => c.code === draft.groupColumn)
  const listed = valuesListed(column)

  const edit = (next: Partial<AnalysisDraft>) => {
    setErrors([])
    setDraft({ ...draft, ...next })
  }

  const run = () => {
    const validation = validateAnalysis(draft)
    if (validation.ok) {
      onRun(validation.analysis)
    } else {
      setErrors(validation.errors)
      requestAnimationFrame(() => errorRef.current?.focus())
    }
  }

  const valueField = (id: string, label: string, value: string, key: 'groupA' | 'groupB') => (
    <div>
      <label htmlFor={id} className="block text-table text-graphite">
        {label}
      </label>
      {listed && column ? (
        <select
          id={id}
          value={value}
          onChange={(e) => edit({ [key]: e.target.value })}
          className={`${control} w-44`}
        >
          <option value="">Choose…</option>
          {column.values.map((v) => (
            <option key={v} value={v}>
              {v}
            </option>
          ))}
        </select>
      ) : (
        <input
          id={id}
          value={value}
          disabled={!column}
          onChange={(e) => edit({ [key]: e.target.value })}
          className={`${control} w-44 disabled:bg-mist`}
        />
      )}
    </div>
  )

  return (
    <div className="space-y-10">
      <div className="max-w-measure">
        <h1 tabIndex={-1} className="text-section font-semibold">
          Check robustness
        </h1>
        <p className="mt-2 text-graphite">
          Choose the main result you plan to report. SurveyDoctor runs it on all respondents, and
          again without the respondents flagged by each rule set, to show whether the result depends
          on them.
        </p>
      </div>

      <fieldset className="max-w-measure space-y-6">
        <legend className="text-sub font-semibold">Your analysis</legend>
        <div className="space-y-2" role="radiogroup" aria-label="Kind of analysis">
          <Choice
            checked={draft.kind === 'group_comparison'}
            disabled={!canGroup}
            onChange={() => edit({ kind: 'group_comparison' })}
            title="Compare two groups"
            detail={
              canGroup
                ? 'A scale score between two groups, e.g. men and women (Welch’s t-test).'
                : 'Not available: the file has no other column to form groups with.'
            }
          />
          <Choice
            checked={draft.kind === 'correlation'}
            disabled={!canCorrelate}
            onChange={() => edit({ kind: 'correlation' })}
            title="Correlate two scales"
            detail={
              canCorrelate
                ? 'How strongly two scale scores go together (Pearson r).'
                : 'Not available: it needs at least two scales.'
            }
          />
        </div>

        {draft.kind === 'group_comparison' ? (
          <div className="space-y-4">
            <div>
              <label htmlFor={ids.scale} className="block font-semibold">
                Scale to compare
              </label>
              <select
                id={ids.scale}
                value={draft.scale}
                onChange={(e) => edit({ scale: e.target.value })}
                className={field}
              >
                {scales.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor={ids.column} className="block font-semibold">
                Column that defines the groups
              </label>
              <select
                id={ids.column}
                value={draft.groupColumn}
                onChange={(e) => edit({ groupColumn: e.target.value, groupA: '', groupB: '' })}
                className={field}
              >
                <option value="">Choose…</option>
                {candidates.map((c) => (
                  <option key={c.code} value={c.code}>
                    {c.header === c.code ? c.code : `${c.code}: ${c.header}`}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex flex-wrap gap-4">
              {valueField(ids.a, 'Group A', draft.groupA, 'groupA')}
              {valueField(ids.b, 'Group B', draft.groupB, 'groupB')}
            </div>
            {column && !listed && (
              <p className="text-table text-graphite">
                This column has many different values, so type the two values exactly as they appear
                in the file.
              </p>
            )}
          </div>
        ) : (
          <div className="flex flex-wrap gap-4">
            {(
              [
                [ids.x, 'First scale', 'scaleX'],
                [ids.y, 'Second scale', 'scaleY'],
              ] as const
            ).map(([id, label, key]) => (
              <div key={id}>
                <label htmlFor={id} className="block font-semibold">
                  {label}
                </label>
                <select
                  id={id}
                  value={draft[key]}
                  onChange={(e) => edit({ [key]: e.target.value })}
                  className={`${control} w-56`}
                >
                  {scales.map((s) => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </select>
              </div>
            ))}
          </div>
        )}
      </fieldset>

      <div className="max-w-measure space-y-4">
        {errors.length > 0 && (
          <div ref={errorRef} tabIndex={-1}>
            <Notice kind="problem" title="Check these before you run the check" role="alert">
              <ul className="list-disc pl-5">
                {errors.map((e) => (
                  <li key={e}>{e}</li>
                ))}
              </ul>
            </Notice>
          </div>
        )}
        <div role="status" aria-live="polite">
          {status.kind === 'loading' && (
            <div className="space-y-1">
              <p className="font-semibold">{status.message}</p>
              {status.waking && <p className="text-graphite">{WAKE_UP_MESSAGE}</p>}
            </div>
          )}
        </div>
        {status.kind === 'error' && (
          <Notice kind="problem" title={status.title} role="alert">
            <p>{status.message}</p>
          </Notice>
        )}
        <div className="flex flex-wrap gap-3">
          <Button variant="primary" onClick={run} disabled={running}>
            Run robustness check
          </Button>
          <Button onClick={onBack} disabled={running}>
            Back to results
          </Button>
        </div>
      </div>

      {result ? (
        <section aria-labelledby="robustness-result" className="space-y-4">
          <div className="border-b border-rule pb-2">
            <h2
              id="robustness-result"
              ref={resultRef}
              tabIndex={-1}
              className="scroll-mt-4 text-section font-semibold"
            >
              Result
            </h2>
            <p className="mt-1">
              <StatusTag status={result.response.robustness.status.status} />
              <span className="text-graphite"> · {result.response.robustness.status.reason}</span>
            </p>
          </div>
          <p className="max-w-measure">{result.response.robustness.sentence}</p>
          <VariantTable robustness={result.response.robustness} />
          {result.response.warnings.length > 0 && (
            <details className="rounded-sm border border-rule">
              <summary className="cursor-pointer px-3 py-2 font-semibold">
                Notes from the checks ({result.response.warnings.length})
              </summary>
              <ul className="list-disc space-y-1 border-t border-rule py-3 pr-3 pl-8">
                {result.response.warnings.map((w) => (
                  <li key={w}>{w}</li>
                ))}
              </ul>
            </details>
          )}
        </section>
      ) : (
        <p className="max-w-measure text-slate">
          No check run yet. The table of results appears here.
        </p>
      )}

      <section aria-labelledby="robustness-downloads" className="space-y-4">
        <h2 id="robustness-downloads" className="text-section font-semibold">
          Downloads
        </h2>
        <Downloads file={file} schema={schema} analysis={result?.analysis ?? null} />
      </section>
    </div>
  )
}

function Choice({
  checked,
  disabled,
  onChange,
  title,
  detail,
}: {
  checked: boolean
  disabled: boolean
  onChange: () => void
  title: string
  detail: string
}) {
  return (
    <label
      className={`flex cursor-pointer items-start gap-3 rounded-sm border px-3 py-2 ${
        checked ? 'border-signal bg-mist' : 'border-rule'
      } ${disabled ? 'cursor-not-allowed text-slate' : ''}`}
    >
      <input
        type="radio"
        name="analysis-kind"
        checked={checked}
        disabled={disabled}
        onChange={onChange}
        className="mt-1 size-4 accent-signal"
      />
      <span>
        <span className="block font-semibold">{title}</span>
        <span className="block text-table text-graphite">{detail}</span>
      </span>
    </label>
  )
}
