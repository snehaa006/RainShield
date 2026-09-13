import { DashboardProvider } from '@/hooks/useDashboard';
import { Header } from '@/components/layout/Header';
import { FloodMap } from '@/components/map/FloodMap';
import { MapControls } from '@/components/map/MapControls';
import { MapLegend } from '@/components/map/MapLegend';
import { MetricsStrip } from '@/components/panels/MetricsStrip';
import { NowcastTimeline } from '@/components/panels/NowcastTimeline';
import { AlertPanel } from '@/components/panels/AlertPanel';
import { WardList } from '@/components/panels/WardList';
import { WhatIfSimulator } from '@/components/panels/WhatIfSimulator';
import { CapPanel } from '@/components/panels/CapPanel';
import { CellInspector } from '@/components/panels/CellInspector';
import { ExposurePanel } from '@/components/panels/ExposurePanel';
import { RainfallTrend } from '@/components/charts/RainfallTrend';
import { ScenarioNote } from '@/components/layout/ScenarioNote';

export default function App() {
  return (
    <DashboardProvider>
      <div className="flex h-full flex-col">
        <Header />

        <main className="grid min-h-0 flex-1 gap-3 overflow-y-auto p-3 scroll-thin
          xl:grid-cols-[320px_minmax(0,1fr)_340px] xl:overflow-hidden">
          {/* Left rail: what is happening and where. */}
          <div className="flex min-h-0 flex-col gap-3 xl:overflow-hidden">
            <AlertPanel />
            <WardList className="min-h-[280px] flex-1" />
          </div>

          {/* Centre: the map and the forecast timeline. */}
          <div className="flex min-h-0 flex-col gap-3">
            <MetricsStrip />
            <NowcastTimeline />
            <div className="relative min-h-[420px] flex-1 overflow-hidden rounded-xl border
              border-surface-border">
              <FloodMap />
              <div className="pointer-events-none absolute inset-x-3 top-3 flex justify-between gap-3">
                <MapControls />
                <ScenarioNote />
              </div>
              <div className="pointer-events-none absolute bottom-8 right-3">
                <MapLegend />
              </div>
            </div>
            <RainfallTrend />
          </div>

          {/* Right rail: act on it. */}
          <div className="flex min-h-0 flex-col gap-3 scroll-thin xl:overflow-y-auto xl:pr-1
            [&>section]:shrink-0">
            <WhatIfSimulator />
            <CellInspector />
            <ExposurePanel />
            <CapPanel />
          </div>
        </main>
      </div>
    </DashboardProvider>
  );
}
