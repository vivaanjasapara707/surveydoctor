import {
  MAX_UPLOAD_BYTES,
  TOO_LARGE_MESSAGE,
  type InspectResponse,
  type SurveySchema,
} from '../api/client'
import { formatBytes } from './format'

export interface UploadState {
  /** Kept in memory only, and sent again with each later request (the API stores nothing). */
  file: File
  source: 'upload' | 'sample'
  inspect: InspectResponse
  /** The sample's schema, used to fill in the Scales step; null for an upload. */
  sampleSchema: SurveySchema | null
}

export type LoadStatus =
  | { kind: 'idle' }
  | { kind: 'loading'; message: string; waking: boolean }
  | { kind: 'error'; title: string; message: string }

/** Problems we can see before sending the file: an empty file, or one over the API's limit.
 *  Everything else (encoding, Excel files, row limit) is checked by the API. */
export function checkFile(file: File): string | null {
  if (file.size === 0) return 'The file is empty. Choose the CSV file with your responses.'
  if (file.size > MAX_UPLOAD_BYTES) {
    return `${TOO_LARGE_MESSAGE} (This file is ${formatBytes(file.size)}.)`
  }
  return null
}
