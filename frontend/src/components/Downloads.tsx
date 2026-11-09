import { useState } from 'react'
import {
  WAKE_UP_MESSAGE,
  downloadFlags,
  downloadReport,
  errorMessage,
  waitForServer,
  type Analysis,
  type Download,
  type SurveySchema,
} from '../api/client'
import { SCHEMA_FILENAME, saveFile, schemaBlob } from '../lib/download'
import { Button } from './Button'
import { Notice } from './Notice'

type Kind = 'report' | 'flags'

type State =
  | { kind: 'idle' }
  | { kind: 'busy'; what: Kind; waking: boolean }
  | { kind: 'error'; what: Kind; message: string }

const BUSY: Record<Kind, string> = {
  report: 'Preparing the report…',
  flags: 'Preparing the flags file…',
}

const FAILED: Record<Kind, string> = {
  report: 'Could not prepare the report',
  flags: 'Could not prepare the flags file',
}

interface DownloadsProps {
  file: File
  schema: SurveySchema
  /** The robustness analysis, if one was checked; the report then includes it. */
  analysis: Analysis | null
}

/** Downloads (BLUEPRINT §7.12, screen 7): the HTML report and the flags CSV are made by the
 *  API from the same file and schema; the schema JSON is made here. */
export function Downloads({ file, schema, analysis }: DownloadsProps) {
  const [state, setState] = useState<State>({ kind: 'idle' })
  const busy = state.kind === 'busy'

  async function fetchAndSave(what: Kind, get: () => Promise<Download>) {
    setState({ kind: 'busy', what, waking: false })
    try {
      await waitForServer({
        onSlow: () => setState((s) => (s.kind === 'busy' ? { ...s, waking: true } : s)),
      })
      const download = await get()
      saveFile(download.blob, download.filename)
      setState({ kind: 'idle' })
    } catch (error) {
      setState({ kind: 'error', what, message: errorMessage(error) })
    }
  }

  return (
    <div className="space-y-4">
      <ul className="space-y-4">
        <li className="space-y-1">
          <Button
            disabled={busy}
            onClick={() =>
              void fetchAndSave('report', () => downloadReport(file, schema, analysis))
            }
          >
            Download report
          </Button>
          <p className="text-table text-graphite">
            One HTML file with every result, chart and limitation
            {analysis ? ', including the robustness check' : ''}. It opens in any browser and prints
            to A4.
          </p>
        </li>
        <li className="space-y-1">
          <Button
            disabled={busy}
            onClick={() => void fetchAndSave('flags', () => downloadFlags(file, schema))}
          >
            Download flags (CSV)
          </Button>
          <p className="text-table text-graphite">
            Every respondent's indices, flags and reasons, for a spreadsheet. Columns that look like
            personal information are never included.
          </p>
        </li>
        <li className="space-y-1">
          <Button disabled={busy} onClick={() => saveFile(schemaBlob(schema), SCHEMA_FILENAME)}>
            Download schema (JSON)
          </Button>
          <p className="text-table text-graphite">
            Your scales and settings, to load again with a later export of the same form.
          </p>
        </li>
      </ul>

      <div role="status" aria-live="polite">
        {state.kind === 'busy' && (
          <div className="space-y-1">
            <p className="font-semibold">{BUSY[state.what]}</p>
            {state.waking && <p className="text-graphite">{WAKE_UP_MESSAGE}</p>}
          </div>
        )}
      </div>
      {state.kind === 'error' && (
        <Notice kind="problem" title={FAILED[state.what]} role="alert">
          <p>{state.message}</p>
        </Notice>
      )}
    </div>
  )
}
