import { lazy, Suspense, useEffect, useRef, useState } from 'react'
import {
  analyze,
  checkRobustness,
  errorMessage,
  getHealth,
  getSample,
  inspectFile,
  sampleFile,
  waitForServer,
  type Analysis,
  type AnalyzeResponse,
  type RobustnessResponse,
  type SurveySchema,
} from './api/client'
import { Button } from './components/Button'
import { StepBar } from './components/StepBar'
import { formatCount } from './lib/format'
import { labelsNeeded, type LabelChoice } from './lib/labels'
import { candidateColumns, draftFromSchema, emptyDraft, type ScaleDraft } from './lib/scales'
import type { StepId, StepState } from './lib/steps'
import { checkFile, type LoadStatus, type UploadState } from './lib/upload'
import { Landing } from './screens/Landing'
import { LabelMapping } from './screens/LabelMapping'
import { ScaleBuilder } from './screens/ScaleBuilder'
import { Upload } from './screens/Upload'

// The Results and Robustness screens carry the chart library and the larger tables (most of
// the code), so they load only when needed and the first page opens faster.
const Results = lazy(() => import('./screens/Results').then((m) => ({ default: m.Results })))
const Robustness = lazy(() =>
  import('./screens/Robustness').then((m) => ({ default: m.Robustness })),
)

type Screen = 'landing' | 'upload' | 'labels' | 'scales' | 'results' | 'robustness'

interface RobustnessResult {
  analysis: Analysis
  response: RobustnessResponse
}

interface Loaded {
  file: File
  source: UploadState['source']
  sampleSchema: SurveySchema | null
}

/** The guided flow and its state. All data lives in React state only: nothing is saved in
 *  the browser, and refreshing the page clears it (BLUEPRINT §7.12). */
export default function App() {
  const [screen, setScreen] = useState<Screen>('landing')
  const [upload, setUpload] = useState<UploadState | null>(null)
  const [status, setStatus] = useState<LoadStatus>({ kind: 'idle' })
  const [labelChoice, setLabelChoice] = useState<LabelChoice | null>(null)
  const [draft, setDraft] = useState<ScaleDraft | null>(null)
  const [runStatus, setRunStatus] = useState<LoadStatus>({ kind: 'idle' })
  const [results, setResults] = useState<AnalyzeResponse | null>(null)
  // The schema the results were made with; robustness and downloads send the same one.
  const [resultSchema, setResultSchema] = useState<SurveySchema | null>(null)
  const [robustness, setRobustness] = useState<RobustnessResult | null>(null)
  const [robustnessStatus, setRobustnessStatus] = useState<LoadStatus>({ kind: 'idle' })
  // Each request gets a number; the result of an older one that finishes late is ignored.
  const requestId = useRef(0)
  const shownScreen = useRef<Screen>(screen)

  // Wake the server while the visitor reads the landing page (it sleeps on the free plan).
  useEffect(() => {
    getHealth().catch(() => undefined)
  }, [])

  // On each new screen, start at the top and move focus to its heading.
  useEffect(() => {
    // Compared with the last screen shown, so a repeated effect run moves nothing.
    if (shownScreen.current === screen) return
    shownScreen.current = screen
    window.scrollTo(0, 0)
    document.querySelector<HTMLElement>('main h1')?.focus()
  }, [screen])

  const needLabels = upload !== null && labelsNeeded(upload.inspect.labels)
  const columns = upload ? candidateColumns(upload.inspect) : []

  /** Results describe the labels and scales they were run with; a change makes them (and
   *  the robustness check built on them) out of date. */
  function clearResults() {
    setResults(null)
    setResultSchema(null)
    setRobustness(null)
    setRobustnessStatus({ kind: 'idle' })
  }

  /** Everything after the upload depends on it, so a new upload clears it all. */
  function clearAfterUpload() {
    setLabelChoice(null)
    setDraft(null)
    setRunStatus({ kind: 'idle' })
    clearResults()
  }

  async function load(getFile: () => Promise<Loaded>, message: string, failTitle: string) {
    const id = ++requestId.current
    const current = () => id === requestId.current
    setUpload(null)
    clearAfterUpload()
    setStatus({ kind: 'loading', message, waking: false })
    try {
      await waitForServer({
        onSlow: () => {
          if (current()) setStatus((s) => (s.kind === 'loading' ? { ...s, waking: true } : s))
        },
      })
      const loaded = await getFile()
      if (!current()) return
      setStatus({ kind: 'loading', message: `Reading ${loaded.file.name}…`, waking: false })
      const inspect = await inspectFile(loaded.file)
      if (!current()) return
      setUpload({ ...loaded, inspect })
      setStatus({ kind: 'idle' })
    } catch (error) {
      if (current()) setStatus({ kind: 'error', title: failTitle, message: errorMessage(error) })
    }
  }

  function handleFile(file: File) {
    const problem = checkFile(file)
    if (problem) {
      requestId.current++
      setUpload(null)
      clearAfterUpload()
      setStatus({ kind: 'error', title: 'Could not use this file', message: problem })
      return
    }
    void load(
      async () => ({ file, source: 'upload', sampleSchema: null }),
      `Sending ${file.name}…`,
      'Could not read the file',
    )
  }

  function handleSample() {
    setScreen('upload')
    void load(
      async () => {
        const sample = await getSample()
        return { file: sampleFile(sample), source: 'sample', sampleSchema: sample.schema }
      },
      'Loading the sample data…',
      'Could not load the sample data',
    )
  }

  /** Open the Scales step, starting from the sample's schema or the suggested columns. */
  function goToScales(choice: LabelChoice | null = labelChoice) {
    if (!upload) return
    const range = choice ? { min: choice.scaleMin, max: choice.scaleMax } : null
    if (!draft) {
      const fromSample = upload.sampleSchema ? draftFromSchema(upload.sampleSchema, columns) : null
      setDraft(fromSample?.ok ? fromSample.draft : emptyDraft(columns, range))
    } else if (range) {
      // Newly confirmed labels set the answer range.
      setDraft({ ...draft, scaleMin: String(range.min), scaleMax: String(range.max) })
    }
    setScreen('scales')
  }

  function confirmLabels(choice: LabelChoice) {
    setLabelChoice(choice)
    clearResults()
    goToScales(choice)
  }

  function editDraft(next: ScaleDraft) {
    setDraft(next)
    clearResults()
    setRunStatus({ kind: 'idle' })
  }

  async function runChecks(schema: SurveySchema) {
    if (!upload) return
    const id = ++requestId.current
    const current = () => id === requestId.current
    const message = `Running checks on ${formatCount(upload.inspect.n_rows)} respondents…`
    setRunStatus({ kind: 'loading', message, waking: false })
    try {
      await waitForServer({
        onSlow: () => {
          if (current()) setRunStatus((s) => (s.kind === 'loading' ? { ...s, waking: true } : s))
        },
      })
      setRunStatus({ kind: 'loading', message, waking: false })
      const response = await analyze(upload.file, schema)
      if (!current()) return
      clearResults()
      setResults(response)
      setResultSchema(schema)
      setRunStatus({ kind: 'idle' })
      setScreen('results')
    } catch (error) {
      if (current()) {
        setRunStatus({
          kind: 'error',
          title: 'The checks could not run',
          message: errorMessage(error),
        })
      }
    }
  }

  async function runRobustness(analysis: Analysis) {
    if (!upload || !resultSchema) return
    const id = ++requestId.current
    const current = () => id === requestId.current
    const message = `Running the analysis with and without flagged respondents…`
    setRobustnessStatus({ kind: 'loading', message, waking: false })
    try {
      await waitForServer({
        onSlow: () => {
          if (current()) {
            setRobustnessStatus((s) => (s.kind === 'loading' ? { ...s, waking: true } : s))
          }
        },
      })
      setRobustnessStatus({ kind: 'loading', message, waking: false })
      const response = await checkRobustness(upload.file, resultSchema, analysis)
      if (!current()) return
      setRobustness({ analysis, response })
      setRobustnessStatus({ kind: 'idle' })
    } catch (error) {
      if (current()) {
        setRobustnessStatus({
          kind: 'error',
          title: 'The robustness check could not run',
          message: errorMessage(error),
        })
      }
    }
  }

  function startOver() {
    requestId.current++
    setUpload(null)
    clearAfterUpload()
    setStatus({ kind: 'idle' })
    setScreen('landing')
  }

  const scalesReachable = upload !== null && (!needLabels || labelChoice !== null)
  const steps: Record<StepId, StepState> = {
    upload: screen === 'upload' ? 'current' : upload ? 'done' : 'available',
    labels: !upload
      ? 'locked'
      : !needLabels
        ? 'skipped'
        : screen === 'labels'
          ? 'current'
          : labelChoice
            ? 'done'
            : 'available',
    scales: !scalesReachable
      ? 'locked'
      : screen === 'scales'
        ? 'current'
        : results
          ? 'done'
          : 'available',
    results: !results ? 'locked' : screen === 'results' ? 'current' : 'available',
    robustness: !results
      ? 'locked'
      : screen === 'robustness'
        ? 'current'
        : robustness
          ? 'done'
          : 'available',
  }

  function selectStep(step: StepId) {
    if (step === 'upload') setScreen('upload')
    if (step === 'labels' && needLabels) setScreen('labels')
    if (step === 'scales' && scalesReachable) goToScales()
    if (step === 'results' && results) setScreen('results')
    if (step === 'robustness' && results) setScreen('robustness')
  }

  return (
    <div className="flex min-h-screen flex-col">
      {/* First stop for keyboard users: jump past the header and step bar. */}
      <a
        href="#main"
        className="sr-only rounded-sm bg-signal px-4 py-2 font-semibold text-paper focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-10"
      >
        Skip to content
      </a>
      <header className="border-b border-rule">
        <div className="mx-auto flex max-w-page flex-wrap items-center justify-between gap-x-8 gap-y-2 px-4 py-3 sm:px-6">
          <p className="text-sub font-semibold">SurveyDoctor</p>
          {screen !== 'landing' && <StepBar states={steps} onSelect={selectStep} />}
        </div>
      </header>

      <main
        id="main"
        tabIndex={-1}
        className="mx-auto w-full max-w-page flex-1 px-4 py-8 focus:outline-none sm:px-6 sm:py-12"
      >
        {screen === 'landing' && (
          <Landing onSample={handleSample} onUpload={() => setScreen('upload')} />
        )}
        {screen === 'upload' && (
          <Upload
            status={status}
            upload={upload}
            labelsNeeded={needLabels}
            onFile={handleFile}
            onSample={handleSample}
            onCheckLabels={() => setScreen('labels')}
            onContinue={() => goToScales()}
          />
        )}
        {screen === 'labels' && upload && (
          <LabelMapping
            labels={upload.inspect.labels}
            confirmed={labelChoice}
            onConfirm={confirmLabels}
            onEdit={() => {
              setLabelChoice(null)
              clearResults()
            }}
            onBack={() => setScreen('upload')}
          />
        )}
        {screen === 'scales' && upload && draft && (
          <ScaleBuilder
            columns={columns}
            questionText={upload.inspect.question_text}
            draft={draft}
            onChange={editDraft}
            labelMap={labelChoice?.labelMap ?? null}
            status={runStatus}
            isSample={upload.source === 'sample'}
            onRun={(schema) => void runChecks(schema)}
            onBack={() => setScreen(needLabels ? 'labels' : 'upload')}
            backLabel={needLabels ? 'Back to answer labels' : 'Back to upload'}
          />
        )}
        {screen === 'results' && results && upload && resultSchema && (
          <Suspense fallback={<p role="status">Loading the results…</p>}>
            <Results
              results={results}
              robustness={robustness}
              file={upload.file}
              schema={resultSchema}
              onChangeScales={() => setScreen('scales')}
              onCheckRobustness={() => setScreen('robustness')}
            />
          </Suspense>
        )}
        {screen === 'robustness' && results && upload && resultSchema && (
          <Suspense fallback={<p role="status">Loading…</p>}>
            <Robustness
              file={upload.file}
              schema={resultSchema}
              columns={columns}
              result={robustness}
              status={robustnessStatus}
              onRun={(analysis) => void runRobustness(analysis)}
              onBack={() => setScreen('results')}
            />
          </Suspense>
        )}
      </main>

      <footer className="border-t border-rule">
        <div className="mx-auto flex max-w-page flex-wrap items-center justify-between gap-x-6 gap-y-1 px-4 py-3 text-small text-slate sm:px-6">
          <p>
            Your data stays in this browser tab and is not stored. Refreshing the page clears it.
          </p>
          {screen !== 'landing' && (
            <Button variant="text" onClick={startOver}>
              Start over
            </Button>
          )}
        </div>
      </footer>
    </div>
  )
}
