import { LAYER_OPTIONS } from '@/components/map/layerPaint';
import { useDashboard } from '@/hooks/useDashboard';
import { Segmented } from '@/components/ui/Segmented';
import { Switch } from '@/components/ui/Switch';
import type { LayerId } from '@/types';

/** Short forms keep the segmented control compact over the map. */
const SHORT_LABELS: Record<LayerId, string> = {
  risk: 'Risk',
  rainfall: 'Rainfall',
  flood: 'Depth',
};

export function MapControls() {
  const { activeLayer, setActiveLayer, showInfrastructure, toggleInfrastructure } = useDashboard();

  return (
    <div className="pointer-events-auto flex flex-wrap items-center gap-3 rounded-[12px] border
      border-surface-border bg-black/70 p-2 backdrop-blur-xl">
      <Segmented
        options={LAYER_OPTIONS.map((option) => ({ id: option.id, label: SHORT_LABELS[option.id] }))}
        value={activeLayer}
        onChange={setActiveLayer}
      />
      <span className="h-4 w-px bg-white/10" />
      <Switch checked={showInfrastructure} onChange={toggleInfrastructure} label="Infrastructure" />
    </div>
  );
}
