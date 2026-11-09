import type { InspectResponse } from '../api/client'

const NUMBER = /^-?\d+(\.\d+)?$/

interface PreviewTableProps {
  preview: InspectResponse['preview']
  /** Original header -> short code, to show the code used in later steps. */
  codes: Record<string, string>
}

/** The first rows of the upload, personal columns already removed by the API. The table
 *  scrolls sideways inside its own box; the page never does (design.md §4). */
export function PreviewTable({ preview, codes }: PreviewTableProps) {
  return (
    <div
      // relative: screen-reader-only text in off-screen cells must stay inside this scroll box.
      className="relative overflow-x-auto rounded-sm border border-rule"
      role="region"
      aria-label={`Preview of the first ${preview.rows.length} rows`}
      tabIndex={0}
    >
      <table className="min-w-full border-collapse text-table">
        <thead className="bg-mist">
          <tr>
            {preview.columns.map((header, i) => (
              <th
                key={i}
                scope="col"
                className="border-b border-rule px-3 py-2 text-left align-bottom font-semibold text-graphite"
              >
                {codes[header] && codes[header] !== header && (
                  <span className="block font-mono text-small font-normal text-slate">
                    {codes[header]}
                  </span>
                )}
                <span className="block max-w-56 truncate" title={header}>
                  {header}
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {preview.rows.map((row, r) => (
            <tr key={r} className="even:bg-mist">
              {row.map((cell, c) => (
                <td
                  key={c}
                  className={`border-b border-rule px-3 py-2 whitespace-nowrap tabular-nums ${
                    cell !== null && NUMBER.test(cell.trim()) ? 'text-right' : 'text-left'
                  }`}
                >
                  {cell === null ? (
                    <>
                      <span aria-hidden="true" className="text-slate">
                        —
                      </span>
                      <span className="sr-only">missing</span>
                    </>
                  ) : (
                    <span className="block max-w-64 truncate" title={cell}>
                      {cell}
                    </span>
                  )}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
