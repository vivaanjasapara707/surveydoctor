/**
 * Calls to the SurveyDoctor API (BLUEPRINT §7.11).
 *
 * Every error becomes an ApiError with a plain-English message: the API's own `{code, message}`
 * when it sent one, otherwise a message about the connection. Types come from schema.ts, which
 * is generated from the API's /openapi.json (`npm run gen:api`).
 */
import type { components } from './schema'

type Schemas = components['schemas']
export type HealthResponse = Schemas['HealthResponse']
export type SampleResponse = Schemas['SampleResponse']
export type InspectResponse = Schemas['InspectResponse']
export type ColumnInfo = Schemas['ColumnModel']
export type LabelDetection = Schemas['LabelDetectionModel']
export type SurveySchema = Schemas['SurveySchemaModel']
export type DurationUnit = SurveySchema['duration_unit']
export type AnalyzeResponse = Schemas['AnalyzeResponse']
export type CheckStatus = Schemas['CheckStatusModel']
export type Verdict = Schemas['VerdictModel']
export type FlaggedRespondent = Schemas['FlaggedRespondentModel']
export type CarelessResult = Schemas['CarelessModel']
export type ScaleReliability = Schemas['ScaleReliabilityModel']
export type StructureResult = Schemas['StructureModel']
export type SensitivityResult = Schemas['SensitivityModel']
export type GroupComparison = Schemas['GroupComparisonModel']
export type Correlation = Schemas['CorrelationModel']
export type Analysis = GroupComparison | Correlation
export type RobustnessResponse = Schemas['RobustnessResponse']
export type VariantResult = Schemas['VariantResultModel']

export const API_URL = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/+$/, '')

/** Upload limits enforced by the API; checked here too so a large file is not sent at all. */
export const MAX_UPLOAD_BYTES = 10 * 1024 * 1024
export const MAX_ROWS = 50_000

export const TOO_LARGE_MESSAGE =
  'The file is larger than 10 MB. Remove columns you do not need (for example free-text ' +
  'answers) or split the responses into smaller files, and upload again.'

export const WAKE_UP_MESSAGE =
  'Starting the analysis server — this can take up to a minute on the free plan.'

const NETWORK_MESSAGE =
  'Could not reach the analysis server. Check your internet connection and try again. If it ' +
  'keeps happening, the server may be down; try again in a few minutes.'

export class ApiError extends Error {
  readonly code: string
  /** HTTP status, or null when no response arrived. */
  readonly status: number | null

  constructor(code: string, message: string, status: number | null) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.status = status
  }
}

/** The message to show for any error thrown while talking to the API. */
export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message
  return NETWORK_MESSAGE
}

function isErrorBody(value: unknown): value is { code: string; message: string } {
  if (typeof value !== 'object' || value === null) return false
  const body = value as Record<string, unknown>
  return typeof body.code === 'string' && typeof body.message === 'string'
}

/** Turn a failed response into an ApiError, using the API's message when it sent one. */
async function responseError(response: Response): Promise<ApiError> {
  try {
    const body: unknown = await response.json()
    if (isErrorBody(body)) return new ApiError(body.code, body.message, response.status)
  } catch {
    // Not JSON (for example a proxy's error page); fall through to the generic message.
  }
  return new ApiError(
    'http_error',
    `The analysis server answered with an error (${response.status}). Try again; if it keeps ` +
      'happening, the server may be down.',
    response.status,
  )
}

async function request(path: string, init?: RequestInit): Promise<Response> {
  let response: Response
  try {
    response = await fetch(`${API_URL}${path}`, init)
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new ApiError('network_error', NETWORK_MESSAGE, null)
  }
  if (!response.ok) throw await responseError(response)
  return response
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await request(path, init)
  return (await response.json()) as T
}

export function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return requestJson<HealthResponse>('/api/health', { signal })
}

export interface WaitOptions {
  /** Called once if the server has not answered after `slowAfterMs`. */
  onSlow?: () => void
  slowAfterMs?: number
  /** Give up after this long. */
  timeoutMs?: number
  /** Pause between attempts when the server is not reachable yet. */
  retryMs?: number
}

const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))

/**
 * Wait until /api/health answers. The free hosting plan puts the server to sleep when idle,
 * and the first request then takes up to a minute (BLUEPRINT §3.3); `onSlow` lets the page
 * say so instead of looking stuck.
 */
export async function waitForServer({
  onSlow,
  slowAfterMs = 3000,
  timeoutMs = 90_000,
  retryMs = 2000,
}: WaitOptions = {}): Promise<void> {
  const deadline = Date.now() + timeoutMs
  const slowTimer = onSlow ? setTimeout(onSlow, slowAfterMs) : undefined
  try {
    for (;;) {
      const controller = new AbortController()
      const attemptTimer = setTimeout(() => controller.abort(), Math.max(deadline - Date.now(), 0))
      try {
        await getHealth(controller.signal)
        return
      } catch (error) {
        // A sleeping server can refuse connections or answer 502/503 while it starts.
        const retryable =
          (error instanceof ApiError && (error.status === null || error.status >= 500)) ||
          (error instanceof DOMException && error.name === 'AbortError')
        if (!retryable) throw error
      } finally {
        clearTimeout(attemptTimer)
      }
      if (Date.now() + retryMs >= deadline) {
        throw new ApiError('server_unreachable', NETWORK_MESSAGE, null)
      }
      await delay(retryMs)
    }
  } finally {
    clearTimeout(slowTimer)
  }
}

export function getSample(): Promise<SampleResponse> {
  return requestJson<SampleResponse>('/api/sample')
}

/** The sample CSV as a File, so it goes through exactly the same steps as an upload. */
export function sampleFile(sample: SampleResponse): File {
  return new File([sample.csv], sample.filename, { type: 'text/csv' })
}

export function inspectFile(file: File): Promise<InspectResponse> {
  const body = new FormData()
  body.append('file', file)
  return requestJson<InspectResponse>('/api/inspect', { method: 'POST', body })
}

/** Every check on the survey. The schema travels as JSON text in a form field, next to the
 *  file, because a file upload cannot also carry a JSON body. */
export function analyze(file: File, schema: SurveySchema): Promise<AnalyzeResponse> {
  return requestJson<AnalyzeResponse>('/api/analyze', {
    method: 'POST',
    body: surveyForm(file, schema),
  })
}

/** The declared analysis on all respondents and without each flag variant, with the verdict
 *  band updated by the result. */
export function checkRobustness(
  file: File,
  schema: SurveySchema,
  analysis: Analysis,
): Promise<RobustnessResponse> {
  const body = surveyForm(file, schema)
  body.append('analysis', JSON.stringify(analysis))
  return requestJson<RobustnessResponse>('/api/robustness', { method: 'POST', body })
}

export interface Download {
  blob: Blob
  filename: string
}

/** The self-contained HTML report; it includes the robustness check when an analysis is
 *  given. */
export function downloadReport(
  file: File,
  schema: SurveySchema,
  analysis: Analysis | null,
): Promise<Download> {
  const body = surveyForm(file, schema)
  if (analysis) body.append('analysis', JSON.stringify(analysis))
  return requestFile('/api/report', body, 'surveydoctor_report.html')
}

/** Every respondent's indices, flags and reasons as CSV (personal columns never included). */
export function downloadFlags(file: File, schema: SurveySchema): Promise<Download> {
  return requestFile('/api/export/flags', surveyForm(file, schema), 'surveydoctor_flags.csv')
}

function surveyForm(file: File, schema: SurveySchema): FormData {
  const body = new FormData()
  body.append('file', file)
  body.append('schema', JSON.stringify(schema))
  return body
}

async function requestFile(path: string, body: FormData, fallback: string): Promise<Download> {
  const response = await request(path, { method: 'POST', body })
  return { blob: await response.blob(), filename: filenameFrom(response, fallback) }
}

/** The file name from `Content-Disposition: attachment; filename="..."`. */
export function filenameFrom(response: Response, fallback: string): string {
  const header = response.headers.get('Content-Disposition') ?? ''
  const match = /filename="?([^";]+)"?/i.exec(header)
  return match ? match[1] : fallback
}
