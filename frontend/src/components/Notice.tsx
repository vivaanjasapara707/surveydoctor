import type { ReactNode } from 'react'

export type NoticeKind = 'clear' | 'review' | 'problem' | 'note'

const KINDS: Record<NoticeKind, { box: string; word: string; icon: string }> = {
  clear: { box: 'border-clear bg-clear-tint', word: 'text-clear', icon: '✓' },
  review: { box: 'border-review bg-review-tint', word: 'text-review', icon: '⚠' },
  problem: { box: 'border-problem bg-problem-tint', word: 'text-problem', icon: '✕' },
  note: { box: 'border-graphite bg-mist', word: 'text-ink', icon: '' },
}

interface NoticeProps {
  kind: NoticeKind
  /** The status word, shown in bold before the message (e.g. "Could not read the file"). */
  title: string
  children?: ReactNode
  /** 'alert' for errors that appear after an action, so screen readers announce them. */
  role?: 'alert' | 'status'
}

/** A note or warning: a 3 px status-coloured left border, the status word in bold, then the
 *  message (design.md §6). The icon and word mean colour is never the only signal. */
export function Notice({ kind, title, children, role }: NoticeProps) {
  const style = KINDS[kind]
  return (
    <div role={role} className={`rounded-sm border-l-[3px] px-4 py-3 ${style.box}`}>
      <p className={`font-semibold ${style.word}`}>
        {style.icon && (
          <span aria-hidden="true" className="mr-2">
            {style.icon}
          </span>
        )}
        {title}
      </p>
      {children && <div className="mt-1 space-y-2 text-ink">{children}</div>}
    </div>
  )
}
