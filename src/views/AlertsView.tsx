import { NowcastTimeline } from '@/components/panels/NowcastTimeline';
import { AlertPanel } from '@/components/panels/AlertPanel';
import { CapPanel } from '@/components/panels/CapPanel';
import { ExposurePanel } from '@/components/panels/ExposurePanel';
import { ConditionsPanel } from '@/components/panels/ConditionsPanel';
import { RiskSummary } from '@/components/panels/RiskSummary';
import { WardList } from '@/components/panels/WardList';

/** Dissemination desk: the alert to issue and who it reaches. */
export function AlertsView() {
  return (
    <div className="grid h-full min-h-0 gap-3 xl:grid-cols-[330px_minmax(0,1fr)_330px]">
      <WardList className="min-h-[300px]" />

      <div className="flex min-h-0 flex-col gap-3">
        <NowcastTimeline />
        <CapPanel className="shrink-0" />
        <ExposurePanel className="min-h-[200px] flex-1" />
      </div>

      <div className="flex min-h-0 flex-col gap-3 overflow-y-auto scroll-thin xl:pr-0.5">
        <AlertPanel />
        <ConditionsPanel />
        <RiskSummary />
      </div>
    </div>
  );
}
