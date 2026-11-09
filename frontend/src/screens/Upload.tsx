import { useState, type ChangeEvent, type DragEvent } from 'react'
import { WAKE_UP_MESSAGE } from '../api/client'
import { Button } from '../components/Button'
import { KeyFigures } from '../components/KeyFigures'
import { Notice } from '../components/Notice'
import { PreviewTable } from '../components/PreviewTable'
import { formatCount, plural } from '../lib/format'
import type { LoadStatus, UploadState } from '../lib/upload'

interface UploadProps {
  status: LoadStatus
  upload: UploadState | null
  labelsNeeded: boolean
  onFile: (file: File) => void
  onSample: () => void
  onCheckLabels: () => void
  onContinue: () => void
}

export function Upload({
  status,
  upload,
  labelsNeeded,
  onFile,
  onSample,
  onCheckLabels,
  onContinue,
}: UploadProps) {
  const loading = status.kind === 'loading'
  const showFile = upload !== null && !loading

  return (
    <div className="space-y-8">
      <div className="max-w-measure">
        <h1 tabIndex={-1} className="text-section font-semibold">
          Upload your survey responses
        </h1>
        <p className="mt-2 text-graphite">
          Upload the responses as a CSV file: one row per respondent, one column per question or
          detail (such as a timestamp).
        </p>
      </div>

      <DropZone onFile={onFile} disabled={loading} primary={!showFile} />
      {!showFile && (
        <p>
          <Button variant="text" onClick={onSample} disabled={loading}>
            Or try the sample data
          </Button>
        </p>
      )}

      <div role="status" aria-live="polite" className="max-w-measure">
        {status.kind === 'loading' && (
          <div className="space-y-2">
            <p className="font-semibold">{status.message}</p>
            {status.waking && <p className="text-graphite">{WAKE_UP_MESSAGE}</p>}
          </div>
        )}
      </div>

      {status.kind === 'error' && (
        <div className="max-w-measure">
          <Notice kind="problem" title={status.title} role="alert">
            <p>{status.message}</p>
          </Notice>
        </div>
      )}

      {showFile && (
        <FileSummary
          upload={upload}
          labelsNeeded={labelsNeeded}
          onCheckLabels={onCheckLabels}
          onContinue={onContinue}
        />
      )}
    </div>
  )
}

function DropZone({
  onFile,
  disabled,
  primary,
}: {
  onFile: (file: File) => void
  disabled: boolean
  primary: boolean
}) {
  const [dragging, setDragging] = useState(false)

  const onDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    setDragging(false)
    const file = event.dataTransfer.files[0]
    if (file && !disabled) onFile(file)
  }

  const onChange = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    // Clear the input so that choosing the same file again still triggers a change.
    event.target.value = ''
    if (file) onFile(file)
  }

  const buttonStyle = primary
    ? 'bg-signal text-paper hover:underline underline-offset-2'
    : 'border border-field bg-paper text-ink hover:bg-mist'

  return (
    <div
      onDragOver={(event) => {
        event.preventDefault()
        if (!disabled) setDragging(true)
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
      className={`rounded-sm border-2 border-dashed px-4 py-8 text-center sm:px-6 sm:py-10 ${
        dragging ? 'border-signal bg-mist' : 'border-field'
      }`}
    >
      <p className="font-semibold">Drag a CSV file here</p>
      <p className="my-2 text-graphite">or</p>
      <label
        className={`inline-flex min-h-10 cursor-pointer items-center justify-center rounded-sm px-4 font-semibold has-focus-visible:outline-2 has-focus-visible:outline-offset-2 has-focus-visible:outline-signal pointer-coarse:min-h-11 ${
          disabled ? 'cursor-not-allowed bg-mist text-slate' : buttonStyle
        }`}
      >
        {primary ? 'Choose a file' : 'Choose a different file'}
        <input
          type="file"
          accept=".csv,text/csv"
          className="sr-only"
          onChange={onChange}
          disabled={disabled}
        />
      </label>
      <p className="mt-3 text-small text-slate">CSV only · up to 10 MB and 50,000 responses</p>
    </div>
  )
}

function FileSummary({
  upload,
  labelsNeeded,
  onCheckLabels,
  onContinue,
}: {
  upload: UploadState
  labelsNeeded: boolean
  onCheckLabels: () => void
  onContinue: () => void
}) {
  const { inspect } = upload
  const suggested = inspect.columns.filter((c) => c.suggested_item).length
  const codes: Record<string, string> = {}
  for (const column of inspect.columns) {
    if (column.code) codes[column.header] = column.code
  }
  const renamed = inspect.preview.columns.some((h) => codes[h] && codes[h] !== h)

  return (
    <section aria-labelledby="file-heading" className="space-y-6">
      <div>
        <h2 id="file-heading" className="text-sub font-semibold">
          {upload.source === 'sample' ? 'Sample data' : 'Your file'}:{' '}
          <span className="font-mono text-body font-normal break-all">{inspect.filename}</span>
        </h2>
        {upload.source === 'sample' && (
          <p className="mt-1 text-graphite">
            Personality questionnaire responses (the bfi dataset from the R package psych).
          </p>
        )}
      </div>

      <KeyFigures
        figures={[
          { label: 'Responses', value: formatCount(inspect.n_rows) },
          { label: 'Columns', value: formatCount(inspect.n_columns) },
          { label: 'Look like rating questions', value: formatCount(suggested) },
          {
            label: 'Personal columns left out',
            value: formatCount(inspect.personal_columns.length),
          },
        ]}
      />

      <div className="max-w-measure">
        {inspect.personal_columns.length > 0 ? (
          <Notice kind="note" title="Personal information left out">
            <p>
              {inspect.personal_columns.length === 1 ? 'This column looks' : 'These columns look'}{' '}
              like names or email addresses.{' '}
              {inspect.personal_columns.length === 1 ? 'It is' : 'They are'} not shown here and
              never used in any check:
            </p>
            <ul className="list-disc pl-5">
              {inspect.personal_columns.map((header) => (
                <li key={header}>{header}</li>
              ))}
            </ul>
          </Notice>
        ) : (
          <Notice kind="note" title="No personal columns found">
            <p>No column looks like names or email addresses.</p>
          </Notice>
        )}
      </div>

      <div className="space-y-2">
        <h3 className="font-semibold">First {plural(inspect.preview.rows.length, 'row')}</h3>
        <PreviewTable preview={inspect.preview} codes={codes} />
        {renamed && (
          <p className="text-small text-slate">
            Long question headers get a short code (shown above the header, such as{' '}
            <span className="font-mono">Q1</span>), which later steps use.
          </p>
        )}
      </div>

      <div className="max-w-measure">
        {labelsNeeded ? (
          <div className="space-y-3">
            <p>
              Some answers are words (for example “Strongly agree”). Next, check which number each
              one stands for.
            </p>
            <Button variant="primary" onClick={onCheckLabels}>
              Check answer labels
            </Button>
          </div>
        ) : (
          <div className="space-y-3">
            <Notice kind="clear" title="Answers are already numbers">
              <p>No answer labels need checking.</p>
            </Notice>
            <Button variant="primary" onClick={onContinue}>
              Continue to scales
            </Button>
          </div>
        )}
      </div>
    </section>
  )
}
