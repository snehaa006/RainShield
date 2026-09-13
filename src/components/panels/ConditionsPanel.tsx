import { metres, mmPerHour } from '@/lib/format';
import { useDashboard } from '@/hooks/useDashboard';
import { Panel } from '@/components/ui/Panel';

/** Current rainfall and inundation conditions across the region. */
export function ConditionsPanel() {
  const { regionSummary, scenario } = useDashboard();

  const items = [
    { label: 'Peak rainfall', value: mmPerHour(regionSummary.peakRainfall), icon: '☔' },
    { label: 'Peak depth', value: metres(regionSummary.peakDepth), icon: '🌊' },
    { label: 'Area flooding', value: `${regionSummary.floodedArea} km²`, icon: '🗺' },
    { label: 'Peak risk', value: regionSummary.peakRisk.toFixed(2), icon: '⚠' },
  ];

  return (
    <Panel
      title="Conditions"
      actions={<span className="text-[11px] text-slate-500">{scenario.name}</span>}
    >
      <div className="grid grid-cols-2 gap-2">
        {items.map((item) => (
          <div key={item.label} className="tile">
            <p className="text-[11px] text-slate-500">
              <span className="mr-1 opacity-70">{item.icon}</span>
              {item.label}
            </p>
            <p className="mt-1 text-[17px] font-semibold tabular-nums tracking-tight text-white">
              {item.value}
            </p>
          </div>
        ))}
      </div>
    </Panel>
  );
}
