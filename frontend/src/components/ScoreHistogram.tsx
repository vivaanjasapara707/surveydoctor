import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { CarelessResult } from '../api/client'
import { formatCount, formatNumber, plural } from '../lib/format'
import { TABLE } from '../lib/status'
import { CHART_FONT_SIZE, COLORS } from '../lib/tokens'
import { ChartFrame } from './ChartFrame'

interface Bin {
  start: number
  end: number
  count: number
}

const tick = { fill: COLORS.graphite, fontSize: CHART_FONT_SIZE }

/** Composite-score histogram: one Signal series, thin bars, no legend (design.md §7). The
 *  bins come from the API, the same as in the HTML report. */
export function ScoreHistogram({
  histogram,
  n,
  note,
}: {
  histogram: CarelessResult['histogram']
  n: number
  /** The API's note on the composite score; it starts "a relative ranking ... not a
   *  probability" (design.md §7). */
  note: string
}) {
  const bins: Bin[] = histogram.counts.map((count, i) => ({
    start: histogram.bin_edges[i],
    end: histogram.bin_edges[i + 1],
    count,
  }))
  const peak = bins.reduce((best, bin) => (bin.count > best.count ? bin : best), bins[0])
  const range = (bin: Bin) => `${formatNumber(bin.start)}–${formatNumber(bin.end)}`

  return (
    <ChartFrame
      title="Composite score distribution"
      description={
        `Bar chart of the composite scores of ${formatCount(n)} respondents in ${bins.length} ` +
        `bins from 0 to 1. The largest bin is ${range(peak)} with ${plural(peak.count, 'respondent')}.`
      }
      caption={note}
      chart={
        <ResponsiveContainer
          width="100%"
          height={240}
          initialDimension={{ width: 640, height: 240 }}
        >
          <BarChart
            data={bins}
            barCategoryGap={2}
            margin={{ top: 8, right: 8, bottom: 28, left: 4 }}
          >
            <CartesianGrid vertical={false} stroke={COLORS.rule} />
            <XAxis
              dataKey="start"
              tickFormatter={(v: number) => formatNumber(v)}
              interval={4}
              tick={tick}
              tickLine={false}
              axisLine={{ stroke: COLORS.rule }}
              label={{
                value: 'Composite score (higher = more unusual in this file)',
                position: 'insideBottom',
                offset: -18,
                fill: COLORS.graphite,
                fontSize: CHART_FONT_SIZE,
              }}
            />
            <YAxis
              allowDecimals={false}
              width={52}
              tick={tick}
              tickLine={false}
              axisLine={false}
              label={{
                value: 'Respondents',
                angle: -90,
                position: 'insideLeft',
                fill: COLORS.graphite,
                fontSize: CHART_FONT_SIZE,
                style: { textAnchor: 'middle' },
              }}
            />
            <Tooltip
              cursor={{ fill: COLORS.rule, fillOpacity: 0.4 }}
              content={({ active, payload }) => {
                const bin = payload?.[0]?.payload as Bin | undefined
                if (!active || !bin) return null
                return (
                  <div className="rounded-sm border border-field bg-paper px-3 py-2 text-table">
                    <p className="font-semibold">Score {range(bin)}</p>
                    <p className="tabular-nums">{plural(bin.count, 'respondent')}</p>
                  </div>
                )
              }}
            />
            <Bar dataKey="count" fill={COLORS.signal} isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      }
      table={
        <div className={TABLE.box}>
          <table className={TABLE.table}>
            <caption className="sr-only">Respondents per composite-score bin</caption>
            <thead className={TABLE.head}>
              <tr>
                <th scope="col" className={TABLE.th}>
                  Composite score
                </th>
                <th scope="col" className={TABLE.thNum}>
                  Respondents
                </th>
              </tr>
            </thead>
            <tbody>
              {bins.map((bin) => (
                <tr key={bin.start}>
                  <th scope="row" className={`${TABLE.td} font-normal tabular-nums`}>
                    {range(bin)}
                  </th>
                  <td className={TABLE.tdNum}>{formatCount(bin.count)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      }
    />
  )
}
