import { LAYER_OPTIONS } from '@/components/map/layerPaint';
import { useDashboard } from '@/hooks/useDashboard';

export function MapControls() {
  const { activeLayer, setActiveLayer, showInfrastructure, toggleInfrastructure } = useDashboard();

  return (
    <div className="pointer-events-auto flex flex-wrap items-center gap-1.5 border
      border-surface-border bg-surface-deep/80 p-1.5 backdrop-blur-md clip-notch
      shadow-[0_0_24px_-10px_rgba(34,211,238,0.8)]">
      <span className="ml-1 mr-0.5 font-mono text-[9px] uppercase tracking-[0.2em] text-hud/60">
        Layers
      </span>
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
      <span className="mx-1 h-4 w-px bg-hud/25" />
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
