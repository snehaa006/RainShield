import { useMemo } from 'react';
import { metres } from '@/lib/format';
import { INFRA_ICONS, INFRA_LABELS, exposedAssets } from '@/lib/infrastructure';
import { useDashboard } from '@/hooks/useDashboard';
import { Panel } from '@/components/ui/Panel';

/** Critical assets sitting in cells the inundation model expects to flood. */
export function ExposurePanel({ className = '' }: { className?: string }) {
  const { cells, region, stations } = useDashboard();
  const exposed = useMemo(
    () => exposedAssets(cells, region, stations),
    [cells, region, stations],
  );

  return (
    <Panel
      title="Infrastructure exposure"
      actions={<span className="text-[11px] text-slate-500">{exposed.length} assets</span>}
      bodyClassName="min-h-0 flex-1 overflow-y-auto scroll-thin px-2 pb-2"
      className={className}
    >
      {exposed.length === 0 ? (
        <p className="p-2 text-[12px] text-slate-500">
          No hospitals, schools, shelters or bridges are in cells above the 0.15 m threshold at
          this horizon.
        </p>
      ) : (
        <ul className="space-y-1">
          {exposed.map((asset) => (
            <li
              key={asset.id}
              className="flex items-center gap-3 rounded-[10px] px-2 py-1.5 transition-colors
                hover:bg-white/[0.05]"
            >
              <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full
                bg-white/[0.07] text-xs">
                {INFRA_ICONS[asset.type]}
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-[12px] text-slate-100">{asset.name}</p>
                <p className="text-[10px] text-slate-500">{INFRA_LABELS[asset.type]}</p>
              </div>
              <span
                className="shrink-0 text-[13px] font-semibold tabular-nums"
                style={{ color: asset.depth >= 0.6 ? '#ff453a' : '#ff9f0a' }}
              >
                {metres(asset.depth)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}
