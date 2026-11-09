import { useId, useRef, useState } from 'react'
import type { LabelDetection } from '../api/client'
import { Button } from '../components/Button'
import { Notice } from '../components/Notice'
import { plural } from '../lib/format'
import {
  initialDraft,
  labelSetName,
  rangeOptions,
  validateLabels,
  type LabelChoice,
  type LabelDraft,
  type LabelRow,
  type LabelValue,
} from '../lib/labels'

interface LabelMappingProps {
  labels: LabelDetection
  /** The choice confirmed earlier, if any; the screen starts from it. */
  confirmed: LabelChoice | null
  onConfirm: (choice: LabelChoice) => void
  /** Called on the first edit after confirming, so the confirmation can be withdrawn. */
  onEdit: () => void
  onBack: () => void
}

/** Answer labels: confirm the proposed text -> number map; unrecognised labels must be mapped
 *  by the user (BLUEPRINT §7.12, screen 3). */
export function LabelMapping({ labels, confirmed, onConfirm, onEdit, onBack }: LabelMappingProps) {
  const [draft, setDraft] = useState<LabelDraft>(() => initialDraft(labels, confirmed))
  const [errors, setErrors] = useState<string[]>([])
  const errorRef = useRef<HTMLDivElement>(null)
  const minId = useId()
  const maxId = useId()

  const edit = (next: LabelDraft) => {
    setDraft(next)
    setErrors([])
    if (confirmed) onEdit()
  }

  const setValue = (key: string, value: LabelValue) =>
    edit({ ...draft, rows: draft.rows.map((row) => (row.key === key ? { ...row, value } : row)) })

  const confirm = () => {
    const result = validateLabels(draft)
    if (result.ok) {
      onConfirm(result.choice)
    } else {
      setErrors(result.errors)
      // Move focus to the list of problems so keyboard and screen-reader users find it.
      requestAnimationFrame(() => errorRef.current?.focus())
    }
  }

  const options = rangeOptions(draft)
  const recognised = draft.rows.filter((r) => r.recognised)
  const unrecognised = draft.rows.filter((r) => !r.recognised)

  return (
    <div className="max-w-measure space-y-8">
      <div>
        <h1 tabIndex={-1} className="text-section font-semibold">
          Check the answer labels
        </h1>
        <p className="mt-2 text-graphite">
          Some answers are words, not numbers. Each word needs a number on the scale before the
          checks can run. Higher numbers should mean more of what the questions ask about: more
          agreement, more often, or more satisfied.
        </p>
      </div>

      <div className="space-y-3">
        {labels.label_set && (
          <Notice kind="note" title={`Recognised: ${labelSetName(labels.label_set)}`}>
            <p>The numbers below are proposed from that set. Check them before you confirm.</p>
          </Notice>
        )}
        {labels.alternatives.length > 0 && (
          <Notice kind="review" title="Your answers also fit another scale">
            <p>
              They also match {labels.alternatives.map(labelSetName).join(' and ')}. If your form
              offered a different number of options, change the scale range and the numbers below.
            </p>
          </Notice>
        )}
        {unrecognised.length > 0 && (
          <Notice
            kind="review"
            title={`${plural(unrecognised.length, 'answer')} ${unrecognised.length === 1 ? 'needs' : 'need'} a number`}
          >
            <p>
              SurveyDoctor does not guess these. Choose a number for each, or choose “Not a rating
              answer” (for example for “Prefer not to say”); those answers then count as missing.
            </p>
          </Notice>
        )}
      </div>

      <fieldset>
        <legend className="text-sub font-semibold">Scale range</legend>
        <p className="mt-1 text-graphite">The lowest and highest number an answer can have.</p>
        <div className="mt-3 flex flex-wrap gap-4">
          <div>
            <label htmlFor={minId} className="block text-table text-graphite">
              Lowest answer
            </label>
            <input
              id={minId}
              inputMode="numeric"
              value={draft.scaleMin}
              onChange={(e) => edit({ ...draft, scaleMin: e.target.value })}
              className="mt-1 min-h-10 w-24 rounded-sm border border-field px-3 tabular-nums"
            />
          </div>
          <div>
            <label htmlFor={maxId} className="block text-table text-graphite">
              Highest answer
            </label>
            <input
              id={maxId}
              inputMode="numeric"
              value={draft.scaleMax}
              onChange={(e) => edit({ ...draft, scaleMax: e.target.value })}
              className="mt-1 min-h-10 w-24 rounded-sm border border-field px-3 tabular-nums"
            />
          </div>
        </div>
      </fieldset>

      {recognised.length > 0 && (
        <LabelTable
          caption="Recognised labels"
          rows={recognised}
          options={options}
          onChange={setValue}
        />
      )}
      {unrecognised.length > 0 && (
        <LabelTable
          caption="Answers that need a number"
          rows={unrecognised}
          options={options}
          onChange={setValue}
        />
      )}

      {errors.length > 0 && (
        <div ref={errorRef} tabIndex={-1}>
          <Notice kind="problem" title="Check these before you confirm" role="alert">
            <ul className="list-disc pl-5">
              {errors.map((error) => (
                <li key={error}>{error}</li>
              ))}
            </ul>
          </Notice>
        </div>
      )}

      {confirmed && errors.length === 0 && (
        <Notice kind="clear" title="Labels confirmed" role="status">
          <p>
            {plural(Object.keys(confirmed.labelMap).length, 'label')} map to numbers{' '}
            {confirmed.scaleMin}–{confirmed.scaleMax}
            {confirmed.notRatings.length > 0 &&
              `; ${plural(confirmed.notRatings.length, 'answer')} will count as missing`}
            .
          </p>
        </Notice>
      )}

      <div className="flex flex-wrap gap-3">
        <Button variant="primary" onClick={confirm}>
          Confirm labels
        </Button>
        <Button onClick={onBack}>Back to upload</Button>
      </div>
    </div>
  )
}

function LabelTable({
  caption,
  rows,
  options,
  onChange,
}: {
  caption: string
  rows: LabelRow[]
  options: number[]
  onChange: (key: string, value: LabelValue) => void
}) {
  return (
    <table className="w-full border-collapse text-table">
      <caption className="mb-2 text-left text-body font-semibold">{caption}</caption>
      <thead className="bg-mist">
        <tr>
          <th scope="col" className="border-b border-rule px-3 py-2 text-left text-graphite">
            Answer text
          </th>
          <th
            scope="col"
            className="w-36 border-b border-rule px-3 py-2 text-left text-graphite sm:w-48"
          >
            Number
          </th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => {
          const outside = typeof row.value === 'number' && !options.includes(row.value)
          return (
            <tr key={row.key} className={row.value === null ? 'bg-review-tint' : undefined}>
              <th scope="row" className="border-b border-rule px-3 py-2 text-left font-normal">
                “{row.key}”
                {row.value === null && (
                  <span className="block text-small font-semibold text-review">needs a number</span>
                )}
              </th>
              <td className="border-b border-rule px-3 py-2">
                <select
                  aria-label={`Number for “${row.key}”`}
                  value={row.value === null ? '' : String(row.value)}
                  onChange={(e) => onChange(row.key, parseChoice(e.target.value))}
                  className="min-h-10 w-full rounded-sm border border-field bg-paper px-2 tabular-nums"
                >
                  {(row.value === null || !row.recognised) && <option value="">Choose…</option>}
                  {outside && (
                    <option value={String(row.value)}>{row.value} (outside the range)</option>
                  )}
                  {options.map((n) => (
                    <option key={n} value={String(n)}>
                      {n}
                    </option>
                  ))}
                  {!row.recognised && <option value="missing">Not a rating answer</option>}
                </select>
              </td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}

function parseChoice(value: string): LabelValue {
  if (value === '') return null
  if (value === 'missing') return 'missing'
  return Number(value)
}
