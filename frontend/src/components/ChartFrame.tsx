import { useState, type ReactNode } from 'react'
import { Button } from './Button'

interface ChartFrameProps {
  title: string
  /** What the chart shows, in numbers, for screen readers (design.md §4 "Charts"). */
  description: string
  caption?: ReactNode
  chart: ReactNode
  table: ReactNode
}

/** A chart with a title, a caption and a "Show as table" toggle (design.md §7). */
export function ChartFrame({ title, description, caption, chart, table }: ChartFrameProps) {
  const [asTable, setAsTable] = useState(false)
  return (
    <figure className="space-y-2">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="font-semibold">{title}</h3>
        <Button variant="text" aria-pressed={asTable} onClick={() => setAsTable(!asTable)}>
          {asTable ? 'Show as chart' : 'Show as table'}
        </Button>
      </div>
      {asTable ? (
        table
      ) : (
        <div role="img" aria-label={description}>
          {chart}
        </div>
      )}
      {caption && <figcaption className="text-table text-graphite">{caption}</figcaption>}
    </figure>
  )
}
