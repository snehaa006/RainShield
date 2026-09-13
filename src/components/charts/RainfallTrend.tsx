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
    <Panel title="Nowcast trend" code="TRD-01" bodyClassName="p-2 pr-4 pt-4">
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
              <stop offset="0%" stopColor="#22d3ee" stopOpacity={0.55} />
              <stop offset="100%" stopColor="#22d3ee" stopOpacity={0.02} />
            </linearGradient>
            {/* Soft bloom so the traces read as emissive, like the reference boards. */}
            <filter id="traceGlow" x="-30%" y="-60%" width="160%" height="240%">
              <feGaussianBlur stdDeviation="3.2" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </defs>
          <CartesianGrid stroke="rgba(56, 189, 248, 0.10)" vertical={false} />
          <XAxis
            dataKey="label"
            tick={{ fill: '#64748b', fontSize: 10, fontFamily: 'JetBrains Mono, monospace' }}
            axisLine={{ stroke: 'rgba(56, 189, 248, 0.25)' }}
            tickLine={false}
          />
          <YAxis
            yAxisId="rain"
            tick={{ fill: '#64748b', fontSize: 10, fontFamily: 'JetBrains Mono, monospace' }}
            axisLine={false}
            tickLine={false}
            width={44}
          />
          <YAxis yAxisId="prob" orientation="right" hide domain={[0, 100]} />
          <Tooltip
            cursor={{ stroke: 'rgba(34, 211, 238, 0.45)', strokeWidth: 1 }}
            contentStyle={{
              background: 'rgba(4, 12, 22, 0.94)',
              border: '1px solid rgba(34, 211, 238, 0.35)',
              borderRadius: 0,
              boxShadow: '0 0 22px -8px rgba(34, 211, 238, 0.9)',
              fontSize: 12,
            }}
            labelStyle={{ color: '#67e8f9', letterSpacing: '0.08em', textTransform: 'uppercase' }}
            formatter={(value: number, name: string) =>
              name.includes('probability') ? [`${value}%`, name] : [`${value} mm/hr`, name]
            }
          />
          <Area
            yAxisId="rain"
            type="monotone"
            dataKey="peakRainfall"
            name="Peak rainfall"
            stroke="#22d3ee"
            strokeWidth={2}
            fill="url(#rainfallFill)"
            filter="url(#traceGlow)"
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
            filter="url(#traceGlow)"
          />
        </ComposedChart>
      </ResponsiveContainer>

      <div className="flex items-center justify-between px-3 pb-1 font-mono text-[10px]
        uppercase tracking-[0.12em] text-slate-500">
        <Legend color="#22d3ee" label="Peak rainfall" />
        <Legend color="#64748b" label="Mean rainfall" />
        <Legend color="#f97316" label="Peak flood prob." />
        <span className="text-hud/50">click to scrub · {LEAD_TIME_LABELS[lead]}</span>
      </div>
    </Panel>
  );
}

function Legend({ color, label }: { color: string; label: string }) {
  return (
    <span className="flex items-center gap-1.5">
      <span
        className="h-1.5 w-3"
        style={{ backgroundColor: color, boxShadow: `0 0 8px 0 ${color}` }}
      />
      {label}
    </span>
  );
}
