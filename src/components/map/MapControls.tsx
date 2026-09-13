import { LAYER_OPTIONS } from '@/components/map/layerPaint';
import { useDashboard } from '@/hooks/useDashboard';

export function MapControls() {
  const { activeLayer, setActiveLayer, showInfrastructure, toggleInfrastructure } = useDashboard();

  return (
    <div className="pointer-events-auto flex flex-wrap items-center gap-1.5 rounded-lg border
      border-surface-border bg-surface/90 p-1.5 backdrop-blur">
      {LAYER_OPTIONS.map((option) => (
        <button
          key={option.id}
          type="button"
          onClick={() => setActiveLayer(option.id)}
          className={`chip ${activeLayer === option.id ? 'chip-active' : ''}`}
        >
          {option.label}
        </button>
      ))}
      <span className="mx-1 h-4 w-px bg-surface-border" />
      <button
        type="button"
        onClick={toggleInfrastructure}
        className={`chip ${showInfrastructure ? 'chip-active' : ''}`}
      >
        Infrastructure
      </button>
    </div>
  );
}
