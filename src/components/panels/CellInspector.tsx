import { CONFIDENCE_COLORS } from '@/lib/config';
import { duration, fullNumber, metres, mmPerHour, percent } from '@/lib/format';
import { WARDS } from '@/lib/grid';
import { useDashboard } from '@/hooks/useDashboard';
import { Panel } from '@/components/ui/Panel';
import { TierBadge } from '@/components/ui/TierBadge';
import { RiskBreakdown } from '@/components/charts/RiskBreakdown';

const LAND_USE_LABELS: Record<string, string> = {
  'urban-dense': 'Dense urban',
  urban: 'Urban',
  periurban: 'Peri-urban',
  vegetation: 'Vegetation',
  water: 'Water body',
};

/** Per-cell drill-down: the model inputs and the risk terms they produced. */
export function CellInspector({ className = '' }: { className?: string }) {
  const { selectedCell, selectCell } = useDashboard();

  if (!selectedCell) {
    return (
      <Panel title="Cell inspector" className={className}>
        <p className="text-[12px] leading-relaxed text-slate-500">
          Select a 1 km cell on the map to inspect its model inputs, flood forecast and the
          weighted terms behind its risk score.
        </p>
      </Panel>
    );
  }

  const ward = WARDS.find((w) => w.id === selectedCell.wardId);

  return (
    <Panel
      title="Cell inspector"
      className={className}
      actions={
        <button type="button" className="btn" onClick={() => selectCell(null)}>
          Clear
        </button>
      }
      bodyClassName="min-h-0 flex-1 space-y-4 overflow-y-auto scroll-thin px-4 pb-4"
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[13px] font-semibold text-white">{selectedCell.id}</p>
          <p className="text-[11px] text-slate-500">
            {ward?.name} · {selectedCell.lat.toFixed(3)}°N {selectedCell.lon.toFixed(3)}°E
          </p>
        </div>
        <TierBadge tier={selectedCell.tier} />
      </div>

      <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-[11px]">
        <Row label="Rainfall (nowcast)" value={mmPerHour(selectedCell.rainfallIntensity)} />
        <Row label="Rainfall (3 hr)" value={`${selectedCell.rainfall3h.toFixed(0)} mm`} />
        <Row label="Flood probability" value={percent(selectedCell.floodProbability)} />
        <Row label="Expected depth" value={metres(selectedCell.waterDepth)} />
        <Row label="Time to inundation" value={duration(selectedCell.timeToInundation)} />
        <Row
          label="Confidence"
          value={selectedCell.confidence}
          color={CONFIDENCE_COLORS[selectedCell.confidence]}
        />
      </dl>

      <div className="border-t border-surface-hairline pt-3">
        <p className="mb-2 text-[11px] font-medium text-slate-400">Static layers</p>
        <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-[11px]">
          <Row label="Elevation" value={`${selectedCell.elevation.toFixed(1)} m`} />
          <Row label="Slope" value={`${selectedCell.slope.toFixed(1)}°`} />
          <Row label="Distance to drainage" value={`${selectedCell.distanceToDrainage.toFixed(2)} km`} />
          <Row label="Land use" value={LAND_USE_LABELS[selectedCell.landUse]} />
          <Row label="Population" value={`${fullNumber(selectedCell.population)} /km²`} />
          <Row label="Infra proximity" value={percent(selectedCell.criticalInfraProximity)} />
        </dl>
      </div>

      <div className="border-t border-surface-hairline pt-3">
        <div className="mb-2 flex items-baseline justify-between">
          <p className="text-[11px] font-medium text-slate-400">Risk contribution</p>
          <p className="text-[15px] font-semibold tabular-nums text-white">
            {selectedCell.risk.total.toFixed(3)}
          </p>
        </div>
        <RiskBreakdown risk={selectedCell.risk} tier={selectedCell.tier} />
      </div>
    </Panel>
  );
}

function Row({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="flex items-baseline justify-between gap-2">
      <dt className="text-slate-500">{label}</dt>
      <dd className="tabular-nums" style={{ color: color ?? '#e2e8f0' }}>
        {value}
      </dd>
    </div>
  );
}
