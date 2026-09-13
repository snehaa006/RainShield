import { Cell, Pie, PieChart, ResponsiveContainer } from 'recharts';
import { TIER_COLORS, TIER_LABELS } from '@/lib/config';
import { useDashboard } from '@/hooks/useDashboard';
import { Panel } from '@/components/ui/Panel';
import type { AlertTier } from '@/types';

const ORDER: AlertTier[] = ['CRITICAL', 'WARNING', 'WATCH', 'NORMAL'];

/** How the region's wards distribute across the four warning tiers. */
export function RiskSummary() {
  const { wardSummaries } = useDashboard();
  const total = wardSummaries.length || 1;

  const data = ORDER.map((tier) => ({
    tier,
    count: wardSummaries.filter((w) => w.tier === tier).length,
  }));

  return (
    <Panel title="Risk summary">
      <div className="flex items-center gap-4">
        <div className="relative h-[104px] w-[104px] shrink-0">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={data}
                dataKey="count"
                innerRadius={34}
                outerRadius={50}
                paddingAngle={2}
                startAngle={90}
                endAngle={-270}
                stroke="none"
                isAnimationActive={false}
              >
                {data.map((entry) => (
                  <Cell key={entry.tier} fill={TIER_COLORS[entry.tier]} />
                ))}
              </Pie>
            </PieChart>
          </ResponsiveContainer>
          <div className="pointer-events-none absolute inset-0 flex flex-col items-center
            justify-center">
            <span className="text-xl font-semibold leading-none tabular-nums text-white">
              {total}
            </span>
            <span className="text-[10px] text-slate-500">wards</span>
          </div>
        </div>

        <ul className="min-w-0 flex-1 space-y-1.5">
          {data.map((entry) => (
            <li key={entry.tier} className="flex items-center gap-2 text-[11px]">
              <span
                className="h-2 w-2 shrink-0 rounded-full"
                style={{ backgroundColor: TIER_COLORS[entry.tier] }}
              />
              <span className="flex-1 text-slate-400">{TIER_LABELS[entry.tier]}</span>
              <span className="tabular-nums text-slate-300">{entry.count}</span>
              <span className="w-9 text-right tabular-nums text-slate-600">
                {Math.round((entry.count / total) * 100)}%
              </span>
            </li>
          ))}
        </ul>
      </div>
    </Panel>
  );
}
