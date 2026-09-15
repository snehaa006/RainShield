export type ViewId =
  | 'dashboard'
  | 'map'
  | 'risk'
  | 'drainage'
  | 'wards'
  | 'alerts'
  | 'feed';

export const VIEWS: { id: ViewId; label: string }[] = [
  { id: 'dashboard', label: 'Dashboard' },
  { id: 'map', label: 'Flood map' },
  { id: 'risk', label: 'Risk model' },
  { id: 'drainage', label: 'Drainage' },
  { id: 'wards', label: 'Wards' },
  { id: 'alerts', label: 'Alerts' },
  { id: 'feed', label: 'Live feed' },
];

export { DashboardView } from '@/views/DashboardView';
export { MapView } from '@/views/MapView';
export { RiskView } from '@/views/RiskView';
export { DrainageView } from '@/views/DrainageView';
export { WardsView } from '@/views/WardsView';
export { AlertsView } from '@/views/AlertsView';
export { FeedView } from '@/views/FeedView';
