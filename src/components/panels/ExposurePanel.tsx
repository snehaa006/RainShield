import { useMemo } from 'react';
import { metres } from '@/lib/format';
import { INFRA_ICONS, INFRA_LABELS, exposedAssets } from '@/lib/infrastructure';
import { useDashboard } from '@/hooks/useDashboard';
import { Panel } from '@/components/ui/Panel';

/** Critical assets sitting in cells the inundation model expects to flood. */
export function ExposurePanel() {
  const { cells } = useDashboard();
  const exposed = useMemo(() => exposedAssets(cells), [cells]);

  return (
    <Panel
      title="Critical infrastructure exposed"
      actions={<span className="text-[11px] text-slate-500">{exposed.length} assets</span>}
      bodyClassName="min-h-0 flex-1 overflow-y-auto scroll-thin p-2"
    >
      {exposed.length === 0 ? (
        <p className="p-2 text-xs text-slate-500">
          No hospitals, schools, shelters or bridges are in cells above the 0.15 m threshold at
          this horizon.
        </p>
      ) : (
        <ul className="space-y-1">
          {exposed.map((asset) => (
            <li
              key={asset.id}
              className="flex items-center gap-3 rounded-md px-2 py-1.5 hover:bg-surface"
            >
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full
                bg-slate-800 text-xs text-slate-300">
                {INFRA_ICONS[asset.type]}
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-xs text-slate-200">{asset.name}</p>
                <p className="text-[10px] text-slate-500">{INFRA_LABELS[asset.type]}</p>
              </div>
              <span
                className="shrink-0 text-xs font-semibold tabular-nums"
                style={{ color: asset.depth >= 0.6 ? '#f87171' : '#fbbf24' }}
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
