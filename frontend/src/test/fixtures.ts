import type { InspectResponse, LabelDetection } from '../api/client'
import inspectJson from './fixtures/inspect_google_forms.json'

/** The API's real /api/inspect response for backend/tests/fixtures/google_forms_sample.csv
 *  (saved in Stage 12). It has a typo label ("Strongly agre") the user must map, a 7-point
 *  alternative, and two personal columns. */
export const inspectGoogleForms = inspectJson as InspectResponse

export const googleFormsLabels: LabelDetection = inspectGoogleForms.labels

/** Labels the API could not match to any known set: no proposal and no range. */
export const unknownLabels: LabelDetection = {
  label_set: null,
  label_map: null,
  scale_min: null,
  scale_max: null,
  unrecognised: ['No', 'Yes'],
  alternatives: [],
}
