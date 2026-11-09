import { motion, useReducedMotion } from 'framer-motion'
import type { Verdict } from '../api/client'
import { STATUS } from '../lib/status'

interface VerdictBandProps {
  verdict: Verdict
  /** Section id for each check that has a section on this screen. */
  sections: Partial<Record<string, string>>
}

/** The memorable element (design.md §5): the overall status as a large word with its icon,
 *  one sentence naming what needs attention, and a chip per check. All of it comes from the
 *  API; the website does not work out any status itself. */
export function VerdictBand({ verdict, sections }: VerdictBandProps) {
  const reduceMotion = useReducedMotion()
  const style = STATUS[verdict.status]
  return (
    // The one animation on the site: a 150 ms fade-in, off when reduced motion is requested.
    <motion.section
      initial={{ opacity: reduceMotion ? 1 : 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: reduceMotion ? 0 : 0.15 }}
      aria-labelledby="verdict-heading"
      className={`rounded-sm border-l-4 px-4 py-5 sm:px-6 ${style.border} ${style.tint}`}
    >
      <h1
        id="verdict-heading"
        tabIndex={-1}
        className={`text-section font-semibold sm:text-verdict ${style.text}`}
      >
        {style.icon && (
          <span aria-hidden="true" className="mr-2">
            {style.icon}
          </span>
        )}
        {verdict.headline}
      </h1>
      <p className="mt-2 text-ink">{verdict.sentence}</p>
      <ul className="mt-4 flex flex-wrap gap-2" aria-label="Checks">
        {verdict.checks.map((check) => {
          const chip = STATUS[check.status]
          const content = (
            <>
              {chip.icon && <span aria-hidden="true">{chip.icon}</span>}
              <span className="font-semibold text-ink">{check.label}</span>
              <span className={chip.text}>{chip.word}</span>
            </>
          )
          const className = `inline-flex min-h-10 items-center gap-2 rounded-sm border bg-paper px-3 text-table pointer-coarse:min-h-11 ${chip.border}`
          const target = sections[check.check]
          return (
            <li key={check.check}>
              {target ? (
                <a
                  href={`#${target}`}
                  title={check.reason}
                  className={`${className} hover:bg-mist`}
                >
                  {content}
                </a>
              ) : (
                <span title={check.reason} className={className}>
                  {content}
                </span>
              )}
            </li>
          )
        })}
      </ul>
    </motion.section>
  )
}
