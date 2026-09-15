import { useState } from 'react';
import { EmergencyAlertOverlay } from '@/components/alerts/EmergencyAlertOverlay';
import { useAlertSystem } from '@/hooks/useAlertSystem';
import { API_BASE } from '@/lib/config';
import { DashboardProvider, useDashboard } from '@/hooks/useDashboard';
import { Header } from '@/components/layout/Header';
import { SimulatedBanner } from '@/components/layout/SimulatedBanner';
import { StatusBar } from '@/components/layout/StatusBar';
import { AlertsView, DashboardView, FeedView, MapView, RiskView, WardsView } from '@/views';
import type { ViewId } from '@/views';

const VIEW_COMPONENTS: Record<ViewId, () => JSX.Element> = {
  dashboard: DashboardView,
  map: MapView,
  risk: RiskView,
  wards: WardsView,
  alerts: AlertsView,
  feed: FeedView,
};

export default function App() {
  return (
    <DashboardProvider>
      <AppShell />
    </DashboardProvider>
  );
}

function AppShell() {
  const [view, setView] = useState<ViewId>('dashboard');
  const { newEvent, activeEvent, clearNewEvent, enableAudio, audioEnabled, muted, setMuted } = useAlertSystem();
  const { selectWard } = useDashboard();

  const reviewEvent = () => {
    if (!newEvent) return;
    selectWard(newEvent.ward.ward.id);
    setView('alerts');
    clearNewEvent();
  };

  return (
    <div className="flex h-full flex-col">
      <Header view={view} onViewChange={setView} />

      {!activeEvent && !audioEnabled && (
        <div className="shrink-0 border-b border-white/10 bg-white/[0.02] px-4 py-1.5">
          <div className="mx-auto flex max-w-[1800px] items-center justify-between gap-3">
            <p className="text-[10px] text-slate-500">Alert engine armed · enable audio so critical events can sound an alarm.</p>
            <button className="btn !px-2.5 !py-1.5 text-[10px]" onClick={() => void enableAudio()}>🔊 Arm alert audio</button>
          </div>
        </div>
      )}

      {activeEvent && (
        <div className="critical-command-banner shrink-0 border-b border-tier-critical/30 bg-tier-critical/[0.08] px-4 py-2">
          <div className="mx-auto flex max-w-[1800px] items-center justify-between gap-3">
            <div className="flex min-w-0 items-center gap-2">
              <span className="h-2.5 w-2.5 shrink-0 animate-soft-pulse rounded-full bg-tier-critical" />
              <p className="truncate text-[11px] font-bold uppercase tracking-wider text-tier-critical">
                Critical event · {activeEvent.ward.ward.name} · {activeEvent.status.replace('_', ' ')}
              </p>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              {!audioEnabled && <button className="btn !border-tier-critical/30 !text-tier-critical" onClick={() => void enableAudio()}>Enable alert audio</button>}
              {audioEnabled && <button className="btn" onClick={() => setMuted(!muted)}>{muted ? 'Unmute alarm' : 'Mute alarm'}</button>}
              <button className="btn btn-accent" onClick={() => { selectWard(activeEvent.ward.ward.id); setView('alerts'); }}>Open incident</button>
            </div>
          </div>
        </div>
      )}

      <main className="min-h-0 flex-1 overflow-y-auto p-3 scroll-thin xl:overflow-hidden">
        <Board view={view} />
      </main>

      <StatusBar />

      {newEvent && (
        <EmergencyAlertOverlay event={newEvent} onReview={reviewEvent} onDismiss={clearNewEvent} />
      )}
    </div>
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
