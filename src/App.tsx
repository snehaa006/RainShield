import { useState } from 'react';
import { API_BASE } from '@/lib/config';
import { DashboardProvider, useDashboard } from '@/hooks/useDashboard';
import { Header } from '@/components/layout/Header';
import { SimulatedBanner } from '@/components/layout/SimulatedBanner';
import { StatusBar } from '@/components/layout/StatusBar';
import {
  AlertsView,
  DashboardView,
  DrainageView,
  FeedView,
  MapView,
  RiskView,
  WardsView,
} from '@/views';
import type { ViewId } from '@/views';

const VIEW_COMPONENTS: Record<ViewId, () => JSX.Element> = {
  dashboard: DashboardView,
  map: MapView,
  risk: RiskView,
  drainage: DrainageView,
  wards: WardsView,
  alerts: AlertsView,
  feed: FeedView,
};

export default function App() {
  const [view, setView] = useState<ViewId>('dashboard');

  return (
    <DashboardProvider>
      <div className="flex h-full flex-col">
        <Header view={view} onViewChange={setView} />

        <main className="min-h-0 flex-1 overflow-y-auto p-3 scroll-thin xl:overflow-hidden">
          <Board view={view} />
        </main>

        <StatusBar />
      </div>
    </DashboardProvider>
  );
}

/**
 * Gates the board on the first load.
 *
 * Every number now comes from the inference API, so there is a real window in
 * which there is nothing to draw — and a real chance the backend is unreachable.
 * Both need to be said plainly rather than rendered as a grid of zeroes.
 */
function Board({ view }: { view: ViewId }) {
  const { isLoading, error, refresh, region, storm } = useDashboard();
  const View = VIEW_COMPONENTS[view];

  if (error) {
    return (
      <Notice title="Cannot reach the inference API">
        <p className="text-[12px] leading-relaxed text-slate-400">{error}</p>
        <p className="mt-3 text-[11px] leading-relaxed text-slate-500">
          Expecting the backend at{' '}
          <code className="rounded bg-white/[0.06] px-1 py-0.5 text-slate-300">
            {API_BASE || window.location.origin}
          </code>
          . Start it with{' '}
          <code className="rounded bg-white/[0.06] px-1 py-0.5 text-slate-300">
            uvicorn rainshield.api.app:app
          </code>{' '}
          from <code className="text-slate-300">backend/</code>, or set{' '}
          <code className="text-slate-300">VITE_API_BASE</code> and rebuild.
        </p>
        <button type="button" className="btn mt-4" onClick={refresh}>
          Retry
        </button>
      </Notice>
    );
  }

  if (isLoading) {
    return (
      <Notice title="Loading live forecast">
        <p className="text-[12px] leading-relaxed text-slate-400">
          Pulling current observations and scoring the 1 km grid.
        </p>
      </Notice>
    );
  }

  // The feed view carries its own banner with the full blurb; everywhere else
  // gets the compact one, so a simulated region is never unlabelled.
  if (region?.simulated && view !== 'feed') {
    return (
      <div className="flex h-full min-h-0 flex-col gap-3">
        <SimulatedBanner storm={storm} compact />
        <div className="min-h-0 flex-1">
          <View />
        </div>
      </div>
    );
  }

  return <View />;
}

function Notice({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="flex h-full items-center justify-center">
      <div className="panel max-w-md p-6 text-center">
        <p className="text-[14px] font-semibold text-white">{title}</p>
        <div className="mt-2">{children}</div>
      </div>
    </div>
  );
}
