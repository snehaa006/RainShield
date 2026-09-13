import { NowcastTimeline } from '@/components/panels/NowcastTimeline';
import { AlertPanel } from '@/components/panels/AlertPanel';
import { WardList } from '@/components/panels/WardList';
import { RiskSummary } from '@/components/panels/RiskSummary';
import { ConditionsPanel } from '@/components/panels/ConditionsPanel';
import { ExposurePanel } from '@/components/panels/ExposurePanel';
import { RainfallTrend } from '@/components/charts/RainfallTrend';

/** Every ward at once, with the selected one expanded beside the grid. */
export function WardsView() {
  return (
    <div className="grid h-full min-h-0 gap-3 xl:grid-cols-[minmax(0,1fr)_330px]">
      <div className="flex min-h-0 flex-col gap-3">
        <NowcastTimeline />
        <WardList variant="grid" className="shrink-0" />

        <div className="grid min-h-[200px] flex-1 gap-3 md:grid-cols-2">
          <RainfallTrend />
          <ExposurePanel />
        </div>
      </div>

      <div className="flex min-h-0 flex-col gap-3 overflow-y-auto scroll-thin xl:pr-0.5">
        <AlertPanel />
        <RiskSummary />
        <ConditionsPanel />
      </div>
    </div>
  );
}
