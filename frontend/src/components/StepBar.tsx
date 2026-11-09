import { STEPS, type StepId, type StepState } from '../lib/steps'

interface StepBarProps {
  states: Record<StepId, StepState>
  onSelect: (step: StepId) => void
}

/** The guided flow's progress (design.md §4): all five steps on wide screens, and
 *  "Step 3 of 5: Scales" below 640 px. */
export function StepBar({ states, onSelect }: StepBarProps) {
  const currentIndex = STEPS.findIndex((s) => states[s.id] === 'current')
  const current = STEPS[currentIndex]

  return (
    <nav aria-label="Progress">
      {current && (
        <p className="text-table text-graphite sm:hidden">
          Step {currentIndex + 1} of {STEPS.length}:{' '}
          <span className="font-semibold text-ink">{current.label}</span>
        </p>
      )}
      <ol className="hidden flex-wrap items-center gap-x-1 gap-y-1 text-table sm:flex">
        {STEPS.map((step, index) => {
          const state = states[step.id]
          return (
            <li key={step.id} className="flex items-center gap-1">
              {index > 0 && (
                <span aria-hidden="true" className="px-1 text-slate">
                  ›
                </span>
              )}
              <StepLabel
                number={index + 1}
                label={step.label}
                state={state}
                onSelect={() => onSelect(step.id)}
              />
            </li>
          )
        })}
      </ol>
    </nav>
  )
}

function StepLabel({
  number,
  label,
  state,
  onSelect,
}: {
  number: number
  label: string
  state: StepState
  onSelect: () => void
}) {
  const text = `${number} ${label}`
  switch (state) {
    case 'current':
      return (
        <span aria-current="step" className="border-b-2 border-signal py-1 font-semibold text-ink">
          {text}
        </span>
      )
    case 'done':
    case 'available':
      return (
        <button
          type="button"
          onClick={onSelect}
          aria-label={state === 'done' ? `${text} (completed)` : undefined}
          className="min-h-10 rounded-sm px-1 text-signal underline underline-offset-2 hover:text-ink pointer-coarse:min-h-11"
        >
          {state === 'done' && <span aria-hidden="true">✓ </span>}
          {text}
        </button>
      )
    case 'skipped':
      return (
        <span className="py-1 text-slate">
          {text} <span className="text-small">(not needed)</span>
        </span>
      )
    case 'locked':
      return <span className="py-1 text-slate">{text}</span>
  }
}
