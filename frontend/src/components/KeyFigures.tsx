export interface KeyFigure {
  label: string
  value: string
}

/** A row of key numbers, e.g. responses and columns in the uploaded file. */
export function KeyFigures({ figures }: { figures: KeyFigure[] }) {
  return (
    <dl className="grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-4">
      {figures.map((figure) => (
        <div key={figure.label} className="border-t border-rule pt-2">
          <dt className="text-table text-graphite">{figure.label}</dt>
          <dd className="text-sub font-semibold tabular-nums">{figure.value}</dd>
        </div>
      ))}
    </dl>
  )
}
