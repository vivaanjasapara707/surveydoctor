import { STATUS, type Status } from '../lib/status'

/** A status as icon + word in its colour, e.g. "⚠ Review". */
export function StatusTag({ status }: { status: Status }) {
  const style = STATUS[status]
  return (
    <span className={`inline-flex items-center gap-1 font-semibold ${style.text}`}>
      {style.icon && <span aria-hidden="true">{style.icon}</span>}
      {style.word}
    </span>
  )
}
