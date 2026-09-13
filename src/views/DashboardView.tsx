import { OverviewPanel } from '@/components/panels/OverviewPanel';
import { RiskSummary } from '@/components/panels/RiskSummary';
import { ConditionsPanel } from '@/components/panels/ConditionsPanel';
import { NowcastTimeline } from '@/components/panels/NowcastTimeline';
import { AlertPanel } from '@/components/panels/AlertPanel';
import { WardList } from '@/components/panels/WardList';
import { ExposurePanel } from '@/components/panels/ExposurePanel';
import { RainfallTrend } from '@/components/charts/RainfallTrend';
import { MapFrame } from '@/views/MapFrame';

/** Situation overview: what is happening, where, and who is exposed. */
export function DashboardView() {
  return (
    <div className="grid gap-3 xl:h-full xl:grid-cols-[300px_minmax(0,1fr)_330px]
      xl:grid-rows-[minmax(0,1fr)_224px]">
      {/* Left rail — region totals. */}
      <div className="flex min-h-0 flex-col gap-3 xl:overflow-y-auto xl:pr-0.5 scroll-thin">
        <OverviewPanel />
        <RiskSummary />
        <ConditionsPanel />
      </div>

      {/* Centre — the map. */}
      <div className="flex min-h-0 flex-col gap-3">
        <NowcastTimeline />
        <MapFrame className="min-h-[380px] flex-1" />
      </div>

      {/* Right rail — the ward that needs attention, then the ranking. */}
      <div className="flex min-h-0 flex-col gap-3 overflow-y-auto scroll-thin xl:pr-0.5">
        <AlertPanel className="shrink-0" />
        <WardList className="min-h-[300px] flex-1" />
      </div>

      {/* Bottom strip — trend and exposure, spanning the full board. */}
      <RainfallTrend className="min-h-[224px] xl:col-span-2" />
      <ExposurePanel className="min-h-[224px]" />
    </div>
  );
}
