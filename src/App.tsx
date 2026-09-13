import { useState } from 'react';
import { DashboardProvider } from '@/hooks/useDashboard';
import { Header } from '@/components/layout/Header';
import { StatusBar } from '@/components/layout/StatusBar';
import { AlertsView, DashboardView, MapView, RiskView, WardsView } from '@/views';
import type { ViewId } from '@/views';

const VIEW_COMPONENTS: Record<ViewId, () => JSX.Element> = {
  dashboard: DashboardView,
  map: MapView,
  risk: RiskView,
  wards: WardsView,
  alerts: AlertsView,
};

export default function App() {
  const [view, setView] = useState<ViewId>('dashboard');
  const View = VIEW_COMPONENTS[view];

  return (
    <DashboardProvider>
      <div className="flex h-full flex-col">
        <Header view={view} onViewChange={setView} />

        <main className="min-h-0 flex-1 overflow-y-auto p-3 scroll-thin xl:overflow-hidden">
          <View />
        </main>

        <StatusBar />
      </div>
    </DashboardProvider>
  );
}
