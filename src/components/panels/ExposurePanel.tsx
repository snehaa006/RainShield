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
      title="Infrastructure exposure"
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
              className="clip-bevel flex items-center gap-3 border border-transparent px-2 py-1.5
                transition-colors hover:border-hud/30 hover:bg-hud/5"
            >
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full
                border border-hud/30 bg-hud/10 text-xs text-cyan-200">
                {INFRA_ICONS[asset.type]}
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-xs text-slate-200">{asset.name}</p>
                <p className="font-mono text-[10px] uppercase tracking-[0.1em] text-slate-500">
                  {INFRA_LABELS[asset.type]}
                </p>
              </div>
              <span
                className="shrink-0 font-display text-sm font-bold tabular-nums"
                style={{
                  color: asset.depth >= 0.6 ? '#f87171' : '#fbbf24',
                  textShadow: `0 0 12px ${asset.depth >= 0.6 ? '#f8717180' : '#fbbf2480'}`,
                }}
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
