export type ViewId = 'dashboard' | 'map' | 'risk' | 'wards' | 'alerts';

export const VIEWS: { id: ViewId; label: string }[] = [
  { id: 'dashboard', label: 'Dashboard' },
  { id: 'map', label: 'Flood map' },
  { id: 'risk', label: 'Risk model' },
  { id: 'wards', label: 'Wards' },
  { id: 'alerts', label: 'Alerts' },
];

export { DashboardView } from '@/views/DashboardView';
export { MapView } from '@/views/MapView';
export { RiskView } from '@/views/RiskView';
export { WardsView } from '@/views/WardsView';
export { AlertsView } from '@/views/AlertsView';
