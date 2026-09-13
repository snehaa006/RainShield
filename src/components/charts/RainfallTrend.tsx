import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { LEAD_TIME_LABELS } from '@/lib/config';
import { useDashboard } from '@/hooks/useDashboard';
import { Panel } from '@/components/ui/Panel';
import type { LeadTime } from '@/types';

/** Region-mean rainfall and flood probability across the forecast horizon. */
export function RainfallTrend() {
  const { regionSeries, lead, setLead } = useDashboard();

  const data = regionSeries.map((point) => ({
    ...point,
    label: LEAD_TIME_LABELS[point.lead],
    floodPercent: Math.round(point.peakFloodProbability * 100),
  }));

  return (
    <Panel title="Nowcast trend" bodyClassName="p-2 pr-4 pt-4">
      <ResponsiveContainer width="100%" height={180}>
        <ComposedChart
          data={data}
          margin={{ top: 4, right: 8, bottom: 0, left: -12 }}
          onClick={(event) => {
            const point = data[event?.activeTooltipIndex ?? -1];
            if (point) setLead(point.lead as LeadTime);
          }}
        >
          <defs>
            <linearGradient id="rainfallFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#38bdf8" stopOpacity={0.45} />
              <stop offset="100%" stopColor="#38bdf8" stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="#1e293b" vertical={false} />
          <XAxis
            dataKey="label"
            tick={{ fill: '#64748b', fontSize: 11 }}
            axisLine={{ stroke: '#233046' }}
            tickLine={false}
          />
          <YAxis
            yAxisId="rain"
            tick={{ fill: '#64748b', fontSize: 11 }}
            axisLine={false}
            tickLine={false}
            width={44}
          />
          <YAxis yAxisId="prob" orientation="right" hide domain={[0, 100]} />
          <Tooltip
            contentStyle={{
              background: '#151d2c',
              border: '1px solid #233046',
              borderRadius: 8,
              fontSize: 12,
            }}
            labelStyle={{ color: '#94a3b8' }}
            formatter={(value: number, name: string) =>
              name.includes('probability') ? [`${value}%`, name] : [`${value} mm/hr`, name]
            }
          />
          <Area
            yAxisId="rain"
            type="monotone"
            dataKey="peakRainfall"
            name="Peak rainfall"
            stroke="#38bdf8"
            strokeWidth={2}
            fill="url(#rainfallFill)"
          />
          <Line
            yAxisId="rain"
            type="monotone"
            dataKey="rainfall"
            name="Mean rainfall"
            stroke="#64748b"
            strokeWidth={1.5}
            strokeDasharray="4 3"
            dot={false}
          />
          <Line
            yAxisId="prob"
            type="monotone"
            dataKey="floodPercent"
            name="Peak flood probability"
            stroke="#f97316"
            strokeWidth={2}
            dot={{ r: 2.5, fill: '#f97316' }}
          />
        </ComposedChart>
      </ResponsiveContainer>

      <div className="flex items-center justify-between px-3 pb-1 text-[11px] text-slate-500">
        <Legend color="#38bdf8" label="Peak rainfall" />
        <Legend color="#64748b" label="Mean rainfall" />
        <Legend color="#f97316" label="Peak flood probability" />
        <span className="text-slate-600">click to scrub · {LEAD_TIME_LABELS[lead]}</span>
      </div>
    </Panel>
  );
}

function Legend({ color, label }: { color: string; label: string }) {
  return (
    <span className="flex items-center gap-1.5">
      <span className="h-1.5 w-3 rounded-full" style={{ backgroundColor: color }} />
      {label}
    </span>
  );
}
