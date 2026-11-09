import type { ButtonHTMLAttributes } from 'react'

type Variant = 'primary' | 'secondary' | 'text'

const VARIANTS: Record<Variant, string> = {
  // One primary action per screen (design.md §4).
  primary:
    'bg-signal px-4 text-paper hover:underline underline-offset-2 disabled:bg-mist disabled:text-slate disabled:no-underline',
  secondary:
    'border border-field bg-paper px-4 text-ink hover:bg-mist disabled:border-rule disabled:text-slate disabled:hover:bg-paper',
  text: 'px-1 text-signal underline underline-offset-2 hover:text-ink disabled:text-slate disabled:no-underline',
}

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
}

export function Button({ variant = 'secondary', className = '', type, ...props }: ButtonProps) {
  return (
    <button
      type={type ?? 'button'}
      className={`inline-flex min-h-10 items-center justify-center gap-2 rounded-sm text-body font-semibold pointer-coarse:min-h-11 disabled:cursor-not-allowed ${VARIANTS[variant]} ${className}`}
      {...props}
    />
  )
}
