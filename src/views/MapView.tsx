import { MetricsStrip } from '@/components/panels/MetricsStrip';
import { NowcastTimeline } from '@/components/panels/NowcastTimeline';
import { CellInspector } from '@/components/panels/CellInspector';
import { ExposurePanel } from '@/components/panels/ExposurePanel';
import { MapFrame } from '@/views/MapFrame';

/** Map-first view: the canvas gets the space, drill-downs sit beside it. */
export function MapView() {
  return (
    <div className="flex h-full min-h-0 flex-col gap-3">
      <MetricsStrip />

      <div className="grid min-h-0 flex-1 gap-3 xl:grid-cols-[minmax(0,1fr)_340px]">
        <div className="flex min-h-0 flex-col gap-3">
          <NowcastTimeline />
          <MapFrame className="min-h-[420px] flex-1" />
        </div>

        <div className="flex min-h-0 flex-col gap-3">
          <CellInspector className="max-h-[60%] shrink-0" />
          <ExposurePanel className="min-h-[200px] flex-1" />
        </div>
      </div>
    </div>
  );
}
