import type {
  AnalyzeResponse,
  InspectResponse,
  LabelDetection,
  RobustnessResponse,
  SurveySchema,
} from '../api/client'
import analyzeBfiJson from './fixtures/analyze_bfi.json'
import inspectBfiJson from './fixtures/inspect_bfi.json'
import inspectJson from './fixtures/inspect_google_forms.json'
import robustnessCorrelationJson from './fixtures/robustness_bfi_correlation.json'
import robustnessGenderJson from './fixtures/robustness_bfi_gender.json'
import sampleSchemaJson from './fixtures/sample_schema_bfi.json'

/** Real /api/robustness responses for the bfi sample (saved in Stage 14): Agreeableness by
 *  gender (1 vs 2), and the Neuroticism–Extraversion correlation. Both are "stable". */
export const robustnessGender = robustnessGenderJson as unknown as RobustnessResponse
export const robustnessCorrelation = robustnessCorrelationJson as unknown as RobustnessResponse

/** The gender check as the API would report a direction change in one variant. Only the
 *  fields the website displays are changed; the numbers are left as they are. Used to test
 *  how "unstable" is shown, which the bfi data does not produce. */
export const robustnessUnstable: RobustnessResponse = {
  ...robustnessGender,
  robustness: {
    ...robustnessGender.robustness,
    verdict: 'unstable',
    changed_variants: ['any_rule'],
    status: {
      check: 'robustness',
      label: 'Robustness',
      status: 'problem',
      reason: 'The direction of the result changes when flagged respondents are excluded.',
    },
    sentence: 'Unstable: test sentence.',
    variants: robustnessGender.robustness.variants.map((v) =>
      v.variant === 'any_rule' ? { ...v, changed: true } : v,
    ),
  },
}

/** Real API responses for the bfi sample (saved in Stage 13): /api/inspect, the schema from
 *  /api/sample, and /api/analyze with that schema. */
export const inspectBfi = inspectBfiJson as InspectResponse
export const sampleSchemaBfi = sampleSchemaJson as SurveySchema
// TypeScript widens JSON to loose types, so the response is cast through unknown.
export const analyzeBfi = analyzeBfiJson as unknown as AnalyzeResponse

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
