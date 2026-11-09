import type { SurveySchema } from '../api/client'

/** Hand a file to the browser to save. Nothing is stored anywhere else. */
export function saveFile(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.append(link)
  link.click()
  link.remove()
  // Revoke after the click has been handled, so the download can start.
  setTimeout(() => URL.revokeObjectURL(url), 0)
}

/** The schema as a JSON file, formatted for reading and editing. */
export function schemaBlob(schema: SurveySchema): Blob {
  return new Blob([JSON.stringify(schema, null, 2) + '\n'], { type: 'application/json' })
}

export const SCHEMA_FILENAME = 'surveydoctor_schema.json'
