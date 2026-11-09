export type StepId = 'upload' | 'labels' | 'scales' | 'results' | 'robustness'

/** current: on screen; done: finished, can go back; available: can go to; locked: not yet
 *  reachable; skipped: not needed for this file. */
export type StepState = 'current' | 'done' | 'available' | 'locked' | 'skipped'

export const STEPS: { id: StepId; label: string }[] = [
  { id: 'upload', label: 'Upload' },
  { id: 'labels', label: 'Labels' },
  { id: 'scales', label: 'Scales' },
  { id: 'results', label: 'Results' },
  { id: 'robustness', label: 'Robustness' },
]
