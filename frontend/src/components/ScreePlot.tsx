import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  type LabelProps,
} from 'recharts'
import type { StructureResult } from '../api/client'
import { formatNumber } from '../lib/format'
import { TABLE } from '../lib/status'
import { CHART_FONT_SIZE, COLORS } from '../lib/tokens'
import { ChartFrame } from './ChartFrame'

type Parallel = NonNullable<StructureResult['parallel']>
type Point = Parallel['scree'][number]

const tick = { fill: COLORS.graphite, fontSize: CHART_FONT_SIZE }

/** A name at the right end of a line, so the lines are labelled by name, not only by colour.
 *  The two lines often end close together, so the upper line's name sits above its end and
 *  the lower line's name below. */
function endLabel(name: string, last: number, above: boolean) {
  function EndLabel(props: LabelProps) {
    const { x, y, index } = props as LabelProps & { index?: number }
    if (index !== last || typeof x !== 'number' || typeof y !== 'number') return null
    return (
      <text x={x + 8} y={y} dy={above ? -6 : 14} fill={COLORS.ink} fontSize={CHART_FONT_SIZE}>
        {name}
      </text>
    )
  }
  return EndLabel
}

/** Scree plot with the parallel-analysis line (design.md §7): observed eigenvalues as a solid
 *  Signal line with dots, the random-data threshold as a dashed Copper line, the suggested
 *  number of factors as a thin Graphite rule. */
export function ScreePlot({ parallel }: { parallel: Parallel }) {
  const points = parallel.scree
  const last = points.length - 1
  const observedOnTop = (points[last]?.observed ?? 0) >= (points[last]?.threshold ?? 0)
  const thresholdName = `Random-data threshold (${parallel.percentile.toFixed(0)}th percentile)`

  return (
    <ChartFrame
      title="Scree plot with parallel analysis"
      description={
        `Scree plot of ${points.length} eigenvalues. The first observed eigenvalue is ` +
        `${formatNumber(points[0]?.observed)}. Parallel analysis suggests ` +
        `${parallel.n_suggested} factor${parallel.n_suggested === 1 ? '' : 's'}: the observed ` +
        'eigenvalues above the random-data threshold.'
      }
      caption={`Factors are suggested while the observed eigenvalue is above the threshold from ${parallel.n_iterations} random data sets.`}
      chart={
        <ResponsiveContainer
          width="100%"
          height={300}
          initialDimension={{ width: 640, height: 300 }}
        >
          <LineChart data={points} margin={{ top: 8, right: 80, bottom: 28, left: 4 }}>
            <CartesianGrid vertical={false} stroke={COLORS.rule} />
            <XAxis
              dataKey="position"
              type="number"
              domain={[1, points.length]}
              allowDecimals={false}
              tick={tick}
              tickLine={false}
              axisLine={{ stroke: COLORS.rule }}
              label={{
                value: 'Factor position',
                position: 'insideBottom',
                offset: -18,
                fill: COLORS.graphite,
                fontSize: CHART_FONT_SIZE,
              }}
            />
            <YAxis
              width={44}
              tick={tick}
              tickLine={false}
              axisLine={false}
              label={{
                value: 'Eigenvalue',
                angle: -90,
                position: 'insideLeft',
                fill: COLORS.graphite,
                fontSize: CHART_FONT_SIZE,
                style: { textAnchor: 'middle' },
              }}
            />
            {parallel.n_suggested > 0 && (
              <ReferenceLine
                x={parallel.n_suggested}
                stroke={COLORS.graphite}
                strokeWidth={1}
                label={(props: LabelProps) => {
                  // Just right of the rule, inside the plot, clear of the y-axis numbers.
                  const box = props.viewBox as { x?: number; y?: number } | undefined
                  if (typeof box?.x !== 'number' || typeof box?.y !== 'number') return null
                  return (
                    <text
                      x={box.x + 6}
                      y={box.y + 14}
                      fill={COLORS.graphite}
                      fontSize={CHART_FONT_SIZE}
                    >
                      Suggested: {parallel.n_suggested}
                    </text>
                  )
                }}
              />
            )}
            <Tooltip
              content={({ active, payload }) => {
                const point = payload?.[0]?.payload as Point | undefined
                if (!active || !point) return null
                return (
                  <div className="rounded-sm border border-field bg-paper px-3 py-2 text-table tabular-nums">
                    <p className="font-semibold">Factor {point.position}</p>
                    <p>Observed: {formatNumber(point.observed)}</p>
                    <p>Threshold: {formatNumber(point.threshold)}</p>
                  </div>
                )
              }}
            />
            <Legend
              verticalAlign="top"
              align="left"
              wrapperStyle={{ fontSize: CHART_FONT_SIZE, color: COLORS.ink, paddingBottom: 8 }}
            />
            <Line
              name="Observed eigenvalues"
              dataKey="observed"
              stroke={COLORS.signal}
              strokeWidth={2}
              dot={{ r: 4, fill: COLORS.signal, stroke: COLORS.signal }}
              isAnimationActive={false}
              label={endLabel('Observed', last, observedOnTop)}
            />
            <Line
              name={thresholdName}
              dataKey="threshold"
              stroke={COLORS.copper}
              strokeWidth={2}
              strokeDasharray="6 3"
              dot={false}
              isAnimationActive={false}
              label={endLabel('Threshold', last, !observedOnTop)}
            />
          </LineChart>
        </ResponsiveContainer>
      }
      table={
        <div className={TABLE.box}>
          <table className={TABLE.table}>
            <caption className="sr-only">Observed eigenvalues and random-data threshold</caption>
            <thead className={TABLE.head}>
              <tr>
                <th scope="col" className={TABLE.th}>
                  Factor position
                </th>
                <th scope="col" className={TABLE.thNum}>
                  Observed eigenvalue
                </th>
                <th scope="col" className={TABLE.thNum}>
                  Threshold
                </th>
              </tr>
            </thead>
            <tbody>
              {points.map((point) => (
                <tr key={point.position}>
                  <th scope="row" className={`${TABLE.td} font-normal tabular-nums`}>
                    {point.position}
                  </th>
                  <td className={TABLE.tdNum}>{formatNumber(point.observed)}</td>
                  <td className={TABLE.tdNum}>{formatNumber(point.threshold)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      }
    />
  )
}
