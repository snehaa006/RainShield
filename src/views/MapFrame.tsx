import { FloodMap } from '@/components/map/FloodMap';
import { MapControls } from '@/components/map/MapControls';
import { MapLegend } from '@/components/map/MapLegend';
import { ScenarioNote } from '@/components/layout/ScenarioNote';

/** The map canvas plus its floating chrome, shared by several views. */
export function MapFrame({ className = '' }: { className?: string }) {
  return (
    <div className={`panel relative overflow-hidden ${className}`}>
      <FloodMap />

      {/* The right margin keeps the card clear of MapLibre's zoom buttons. */}
      <div className="pointer-events-none absolute inset-x-3 top-3 flex justify-between gap-3
        pr-10">
        <MapControls />
        <ScenarioNote />
      </div>
      <div className="pointer-events-none absolute bottom-8 right-3">
        <MapLegend />
      </div>
    </div>
  );
}
