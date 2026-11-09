import { useEffect, useRef, useState } from 'react'
import {
  errorMessage,
  getHealth,
  getSample,
  inspectFile,
  sampleFile,
  waitForServer,
  type SurveySchema,
} from './api/client'
import { Button } from './components/Button'
import { StepBar } from './components/StepBar'
import { labelsNeeded, type LabelChoice } from './lib/labels'
import type { StepId, StepState } from './lib/steps'
import { checkFile, type LoadStatus, type UploadState } from './lib/upload'
import { Landing } from './screens/Landing'
import { LabelMapping } from './screens/LabelMapping'
import { Upload } from './screens/Upload'

type Screen = 'landing' | 'upload' | 'labels'

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
  // Each load gets a number; results of an older load that finishes late are ignored.
  const loadId = useRef(0)
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

  async function load(getFile: () => Promise<Loaded>, message: string, failTitle: string) {
    const id = ++loadId.current
    const current = () => id === loadId.current
    setUpload(null)
    setLabelChoice(null)
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
      loadId.current++
      setUpload(null)
      setLabelChoice(null)
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

  function startOver() {
    loadId.current++
    setUpload(null)
    setLabelChoice(null)
    setStatus({ kind: 'idle' })
    setScreen('landing')
  }

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
    scales: 'locked',
    results: 'locked',
    robustness: 'locked',
  }

  function selectStep(step: StepId) {
    if (step === 'upload') setScreen('upload')
    if (step === 'labels' && needLabels) setScreen('labels')
  }

  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b border-rule">
        <div className="mx-auto flex max-w-page flex-wrap items-center justify-between gap-x-8 gap-y-2 px-4 py-3 sm:px-6">
          <p className="text-sub font-semibold">SurveyDoctor</p>
          {screen !== 'landing' && <StepBar states={steps} onSelect={selectStep} />}
        </div>
      </header>

      <main className="mx-auto w-full max-w-page flex-1 px-4 py-8 sm:px-6 sm:py-12">
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
          />
        )}
        {screen === 'labels' && upload && (
          <LabelMapping
            labels={upload.inspect.labels}
            confirmed={labelChoice}
            onConfirm={setLabelChoice}
            onEdit={() => setLabelChoice(null)}
            onBack={() => setScreen('upload')}
          />
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
