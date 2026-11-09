import type { CheckStatus } from '../api/client'

export type Status = CheckStatus['status']

/** Each status has an icon and a word as well as a colour (design.md §1 rule 3, §5). */
export const STATUS: Record<
  Status,
  { icon: string; word: string; text: string; tint: string; border: string }
> = {
  clear: {
    icon: '✓',
    word: 'No concern',
    text: 'text-clear',
    tint: 'bg-clear-tint',
    border: 'border-clear',
  },
  review: {
    icon: '⚠',
    word: 'Review',
    text: 'text-review',
    tint: 'bg-review-tint',
    border: 'border-review',
  },
  problem: {
    icon: '✕',
    word: 'Serious concern',
    text: 'text-problem',
    tint: 'bg-problem-tint',
    border: 'border-problem',
  },
  not_checked: {
    icon: '',
    word: 'Not checked',
    text: 'text-slate',
    tint: 'bg-mist',
    border: 'border-rule',
  },
}

/** Table cell classes shared by the result tables (design.md §6). */
export const TABLE = {
  table: 'min-w-full border-collapse text-table',
  head: 'bg-mist',
  th: 'border-b border-rule px-3 py-2 text-left align-bottom font-semibold text-graphite',
  thNum: 'border-b border-rule px-3 py-2 text-right align-bottom font-semibold text-graphite',
  // text-left: browsers centre row-header (th) cells by default.
  td: 'border-b border-rule px-3 py-2 text-left align-top',
  tdNum: 'border-b border-rule px-3 py-2 text-right align-top tabular-nums whitespace-nowrap',
  box: 'relative overflow-x-auto rounded-sm border border-rule',
}
