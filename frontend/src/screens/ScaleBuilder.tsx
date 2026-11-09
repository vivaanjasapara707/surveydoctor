import { useId, useRef, useState, type ChangeEvent } from 'react'
import { WAKE_UP_MESSAGE, type SurveySchema } from '../api/client'
import { Button } from '../components/Button'
import { Notice } from '../components/Notice'
import { SCHEMA_FILENAME, saveFile, schemaBlob } from '../lib/download'
import { plural } from '../lib/format'
import {
  DURATION_UNITS,
  buildSchema,
  draftFromSchema,
  newScaleId,
  numericAnswers,
  removeScale,
  scaleItems,
  setIncluded,
  validateDraft,
  type ColumnChoice,
  type ScaleDraft,
} from '../lib/scales'
import type { LoadStatus } from '../lib/upload'

interface ScaleBuilderProps {
  columns: ColumnChoice[]
  questionText: Record<string, string>
  draft: ScaleDraft
  onChange: (draft: ScaleDraft) => void
  /** Confirmed answer labels, or null when the answers are numbers. */
  labelMap: Record<string, number> | null
  status: LoadStatus
  isSample: boolean
  onRun: (schema: SurveySchema) => void
  onBack: () => void
  backLabel: string
}

const input = 'min-h-10 rounded-sm border border-field bg-paper px-3 pointer-coarse:min-h-11'
const th = 'border-b border-rule px-3 py-2 text-left align-bottom font-semibold text-graphite'
const td = 'border-b border-rule px-3 py-2 align-top'

/** Scales: pick the question columns, group them into scales, mark reverse-worded questions,
 *  set the answer range; import or export the schema as JSON (BLUEPRINT §7.12, screen 4). */
export function ScaleBuilder({
  columns,
  questionText,
  draft,
  onChange,
  labelMap,
  status,
  isSample,
  onRun,
  onBack,
  backLabel,
}: ScaleBuilderProps) {
  const [errors, setErrors] = useState<string[]>([])
  const [fileMessage, setFileMessage] = useState<string | null>(null)
  const errorRef = useRef<HTMLDivElement>(null)
  const ids = { min: useId(), max: useId(), id: useId(), time: useId(), unit: useId() }
  const running = status.kind === 'loading'

  const edit = (next: ScaleDraft) => {
    setErrors([])
    setFileMessage(null)
    onChange(next)
  }

  const check = (): string[] => {
    const problems = validateDraft(draft, columns, labelMap)
    setErrors(problems)
    if (problems.length > 0) requestAnimationFrame(() => errorRef.current?.focus())
    return problems
  }

  const run = () => {
    if (check().length === 0) onRun(buildSchema(draft, columns, questionText, labelMap))
  }

  const exportSchema = () => {
    if (check().length > 0) return
    saveFile(schemaBlob(buildSchema(draft, columns, questionText, labelMap)), SCHEMA_FILENAME)
  }

  const importSchema = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    let parsed: unknown
    try {
      parsed = JSON.parse(await file.text())
    } catch {
      setFileMessage(
        `${file.name} is not a valid JSON file. Choose a schema saved by SurveyDoctor.`,
      )
      return
    }
    if (!looksLikeSchema(parsed)) {
      setFileMessage(
        `${file.name} is not a SurveyDoctor schema: it needs “items”, “scales”, ` +
          '“reverse_items”, “scale_min” and “scale_max”.',
      )
      return
    }
    const result = draftFromSchema(parsed, columns)
    if (!result.ok) {
      setFileMessage(result.error)
      return
    }
    setErrors([])
    setFileMessage(null)
    onChange(result.draft)
  }

  const nonItems = columns.filter((c) => !draft.included.includes(c.code))
  const answers = numericAnswers(draft, columns)
  const unassigned = draft.included.filter((code) => !draft.assignment[code]).length

  return (
    <div className="space-y-10">
      <div className="max-w-measure">
        <h1 tabIndex={-1} className="text-section font-semibold">
          Build your scales
        </h1>
        <p className="mt-2 text-graphite">
          Tick the columns that are rating questions, group them into scales, and mark the questions
          worded in the opposite direction. SurveyDoctor never guesses these.
        </p>
        {isSample && (
          <div className="mt-4">
            <Notice kind="note" title="Sample scales filled in">
              <p>
                The sample's five personality scales and its reverse-worded questions are already
                set up. Change anything you like, or run the checks as they are.
              </p>
            </Notice>
          </div>
        )}
      </div>

      <section aria-labelledby="scales-heading" className="max-w-measure space-y-3">
        <h2 id="scales-heading" className="text-sub font-semibold">
          Scales
        </h2>
        <p className="text-graphite">
          A scale is a group of questions that measure the same thing, such as “Teamwork”. Each
          scale needs at least two questions.
        </p>
        {draft.scales.length === 0 && (
          <p className="text-slate">No scales yet. Add one, then choose its questions below.</p>
        )}
        <ul className="space-y-2">
          {draft.scales.map((scale, index) => (
            <li key={scale.id} className="flex flex-wrap items-center gap-3">
              <input
                aria-label={`Name of scale ${index + 1}`}
                value={scale.name}
                placeholder={`Scale ${index + 1}`}
                onChange={(e) =>
                  edit({
                    ...draft,
                    scales: draft.scales.map((s) =>
                      s.id === scale.id ? { ...s, name: e.target.value } : s,
                    ),
                  })
                }
                className={`${input} w-64 max-w-full`}
              />
              <span className="text-table text-graphite tabular-nums">
                {plural(scaleItems(draft, scale.id, columns).length, 'question')}
              </span>
              <Button
                variant="text"
                onClick={() => edit(removeScale(draft, scale.id))}
                aria-label={`Remove ${scale.name.trim() || `scale ${index + 1}`}`}
              >
                Remove
              </Button>
            </li>
          ))}
        </ul>
        <Button
          onClick={() =>
            edit({ ...draft, scales: [...draft.scales, { id: newScaleId(), name: '' }] })
          }
        >
          Add a scale
        </Button>
      </section>

      <section aria-labelledby="questions-heading" className="space-y-3">
        <div className="max-w-measure">
          <h2 id="questions-heading" className="text-sub font-semibold">
            Questions
          </h2>
          <p className="mt-1 text-graphite">
            Columns that look like rating questions are ticked already. Questions without a scale
            are still used to find careless answers. A reverse-worded question is one where agreeing
            means less of what the scale measures (e.g. “I prefer to work alone” in a teamwork
            scale).
          </p>
        </div>
        <div
          className="relative overflow-x-auto rounded-sm border border-rule"
          role="region"
          aria-label="Questions and their scales"
          tabIndex={0}
        >
          <table className="min-w-full border-collapse text-table">
            <thead className="bg-mist">
              <tr>
                <th scope="col" className={th}>
                  Question
                </th>
                <th scope="col" className={th}>
                  Answers in the file
                </th>
                <th scope="col" className={th}>
                  Scale
                </th>
                <th scope="col" className={th}>
                  Reverse-worded
                </th>
              </tr>
            </thead>
            <tbody>
              {columns.map((column) => {
                const included = draft.included.includes(column.code)
                const otherRole =
                  column.code === draft.idColumn || column.code === draft.durationColumn
                return (
                  <tr key={column.code} className={included ? undefined : 'text-slate'}>
                    <td className={td}>
                      <label className="flex min-w-56 cursor-pointer items-start gap-2">
                        <input
                          type="checkbox"
                          checked={included}
                          disabled={otherRole}
                          onChange={(e) => edit(setIncluded(draft, column.code, e.target.checked))}
                          className="mt-1 size-4 accent-signal"
                        />
                        <span>
                          <span className="block font-mono text-small">{column.code}</span>
                          {column.header !== column.code && (
                            <span className="block max-w-80">{column.header}</span>
                          )}
                          {otherRole && (
                            <span className="block text-small">
                              Used as the {column.code === draft.idColumn ? 'ID' : 'time'} column
                            </span>
                          )}
                        </span>
                      </label>
                    </td>
                    <td className={`${td} max-w-56`}>
                      <span className="block truncate" title={column.values.join(', ')}>
                        {column.values.join(', ')}
                        {column.nDistinct > column.values.length && ', …'}
                      </span>
                    </td>
                    <td className={td}>
                      <select
                        aria-label={`Scale for ${column.code}`}
                        value={draft.assignment[column.code] ?? ''}
                        disabled={!included}
                        onChange={(e) => {
                          const assignment = { ...draft.assignment }
                          if (e.target.value) assignment[column.code] = e.target.value
                          else delete assignment[column.code]
                          edit({ ...draft, assignment })
                        }}
                        className={`${input} w-44 disabled:bg-mist disabled:text-slate`}
                      >
                        <option value="">No scale</option>
                        {draft.scales.map((scale, index) => (
                          <option key={scale.id} value={scale.id}>
                            {scale.name.trim() || `Scale ${index + 1}`}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className={td}>
                      <label className="inline-flex min-h-10 cursor-pointer items-center gap-2">
                        <input
                          type="checkbox"
                          aria-label={`${column.code} is reverse-worded`}
                          checked={draft.reverse.includes(column.code)}
                          disabled={!included}
                          onChange={(e) =>
                            edit({
                              ...draft,
                              reverse: e.target.checked
                                ? [...draft.reverse, column.code]
                                : draft.reverse.filter((c) => c !== column.code),
                            })
                          }
                          className="size-4 accent-signal"
                        />
                        <span aria-hidden="true">Reverse</span>
                      </label>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
        <p className="text-table text-graphite">
          {plural(draft.included.length, 'question')} ticked
          {unassigned > 0 && `, ${formatUnassigned(unassigned)}`}; {draft.reverse.length}{' '}
          reverse-worded.
        </p>
      </section>

      <fieldset className="max-w-measure">
        <legend className="text-sub font-semibold">Answer range</legend>
        <p className="mt-1 text-graphite">
          The lowest and highest answer a question can have.{' '}
          {labelMap
            ? 'It comes from the answer labels you confirmed.'
            : answers.length > 0 && `Answers seen in the ticked questions: ${answers.join(', ')}.`}
        </p>
        <div className="mt-3 flex flex-wrap gap-4">
          <div>
            <label htmlFor={ids.min} className="block text-table text-graphite">
              Lowest answer
            </label>
            <input
              id={ids.min}
              inputMode="numeric"
              value={draft.scaleMin}
              onChange={(e) => edit({ ...draft, scaleMin: e.target.value })}
              className={`${input} mt-1 w-24 tabular-nums`}
            />
          </div>
          <div>
            <label htmlFor={ids.max} className="block text-table text-graphite">
              Highest answer
            </label>
            <input
              id={ids.max}
              inputMode="numeric"
              value={draft.scaleMax}
              onChange={(e) => edit({ ...draft, scaleMax: e.target.value })}
              className={`${input} mt-1 w-24 tabular-nums`}
            />
          </div>
        </div>
      </fieldset>

      <fieldset className="max-w-measure space-y-4">
        <legend className="text-sub font-semibold">Other columns (optional)</legend>
        <div>
          <label htmlFor={ids.id} className="block font-semibold">
            Respondent ID
          </label>
          <p className="text-table text-graphite">
            Used to name flagged respondents. Without one, they are named by their row in the CSV.
          </p>
          <select
            id={ids.id}
            value={draft.idColumn}
            onChange={(e) => edit({ ...draft, idColumn: e.target.value })}
            className={`${input} mt-1 w-64 max-w-full`}
          >
            <option value="">None</option>
            {nonItems.map((c) => (
              <option key={c.code} value={c.code}>
                {columnLabel(c)}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor={ids.time} className="block font-semibold">
            Completion time
          </label>
          <p className="text-table text-graphite">
            Total time each respondent took. Used to find answers that were too fast.
          </p>
          <div className="mt-1 flex flex-wrap gap-3">
            <select
              id={ids.time}
              value={draft.durationColumn}
              onChange={(e) => edit({ ...draft, durationColumn: e.target.value })}
              className={`${input} w-64 max-w-full`}
            >
              <option value="">None</option>
              {nonItems.map((c) => (
                <option key={c.code} value={c.code}>
                  {columnLabel(c)}
                </option>
              ))}
            </select>
            {draft.durationColumn && (
              <>
                <label htmlFor={ids.unit} className="sr-only">
                  Unit of the completion time
                </label>
                <select
                  id={ids.unit}
                  value={draft.durationUnit}
                  onChange={(e) =>
                    edit({ ...draft, durationUnit: e.target.value as ScaleDraft['durationUnit'] })
                  }
                  className={`${input} w-44`}
                >
                  {DURATION_UNITS.map((unit) => (
                    <option key={unit} value={unit}>
                      {unit}
                    </option>
                  ))}
                </select>
              </>
            )}
          </div>
        </div>
      </fieldset>

      <section aria-labelledby="schema-file-heading" className="max-w-measure space-y-3">
        <h2 id="schema-file-heading" className="text-sub font-semibold">
          Schema file
        </h2>
        <p className="text-graphite">
          Save this setup as a JSON file to reuse it with a later export of the same form, or load
          one you saved before.
        </p>
        <div className="flex flex-wrap gap-3">
          <Button onClick={exportSchema}>Download schema</Button>
          <label className="inline-flex min-h-10 cursor-pointer items-center justify-center rounded-sm border border-field bg-paper px-4 font-semibold hover:bg-mist has-focus-visible:outline-2 has-focus-visible:outline-offset-2 has-focus-visible:outline-signal pointer-coarse:min-h-11">
            Load a schema file
            <input
              type="file"
              accept=".json,application/json"
              className="sr-only"
              onChange={(e) => void importSchema(e)}
            />
          </label>
        </div>
        {fileMessage && (
          <Notice kind="problem" title="Could not load the schema" role="alert">
            <p>{fileMessage}</p>
          </Notice>
        )}
      </section>

      <div className="max-w-measure space-y-4">
        {errors.length > 0 && (
          <div ref={errorRef} tabIndex={-1}>
            <Notice kind="problem" title="Check these before you run the checks" role="alert">
              <ul className="list-disc pl-5">
                {errors.map((error) => (
                  <li key={error}>{error}</li>
                ))}
              </ul>
            </Notice>
          </div>
        )}
        <div role="status" aria-live="polite">
          {status.kind === 'loading' && (
            <div className="space-y-2">
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
            Run checks
          </Button>
          <Button onClick={onBack} disabled={running}>
            {backLabel}
          </Button>
        </div>
      </div>
    </div>
  )
}

function columnLabel(column: ColumnChoice): string {
  return column.header === column.code ? column.code : `${column.code}: ${column.header}`
}

function formatUnassigned(n: number): string {
  return `${n} without a scale`
}

function looksLikeSchema(value: unknown): value is SurveySchema {
  if (typeof value !== 'object' || value === null) return false
  const v = value as Record<string, unknown>
  return (
    Array.isArray(v.items) &&
    v.items.every((i) => typeof i === 'string') &&
    typeof v.scales === 'object' &&
    v.scales !== null &&
    !Array.isArray(v.scales) &&
    Object.values(v.scales).every(
      (s) => Array.isArray(s) && s.every((i) => typeof i === 'string'),
    ) &&
    Array.isArray(v.reverse_items) &&
    Number.isInteger(v.scale_min) &&
    Number.isInteger(v.scale_max)
  )
}
