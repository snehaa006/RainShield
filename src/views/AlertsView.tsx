import { useMemo, useState } from 'react';
import { buildCapAlert, capToXml } from '@/lib/cap';
import { compactNumber, duration, metres, percent } from '@/lib/format';
import { useDashboard } from '@/hooks/useDashboard';
import { useAlertSystem } from '@/hooks/useAlertSystem';
import { Panel } from '@/components/ui/Panel';
import { TierBadge } from '@/components/ui/TierBadge';
import { Segmented } from '@/components/ui/Segmented';

const CHANNELS = [
  ['SMS cell broadcast', 'Telecom gateway', 96],
  ['Mobile app', 'Citizen notification', 94],
  ['Web portal', 'Public dashboard', 100],
  ['Authority API', 'SDMA / NDMA gateway', 100],
  ['Siren network', 'Ward warning system', 88],
] as const;

export function AlertsView() {
  const { wardSummaries, region, lead } = useDashboard();
  const { events, activeEvent, updateStatus, isSimulating } = useAlertSystem();
  const [tab, setTab] = useState<'operations' | 'cap'>('operations');
  const highest = wardSummaries[0] ?? null;
  const previewWard = activeEvent?.ward ?? highest;
  const preview = useMemo(() => previewWard ? buildCapAlert(previewWard, region) : null, [previewWard, region]);

  const approve = (id: string) => updateStatus(id, 'APPROVED');
  // The backend's broadcast endpoint dispatches the channels and lands the
  // alert on ACTIVE itself, so this is a single call; the poll picks the new
  // status up. The previous follow-up timer asked for 'ACTIVE', which the
  // action map did not handle and which therefore fired a cancel request.
  const broadcast = (id: string) => updateStatus(id, 'BROADCASTING');

  const critical = events.filter((event) => event.tier === 'CRITICAL' && event.status !== 'RESOLVED').length;
  const review = events.filter((event) => event.status === 'UNDER_REVIEW').length;

  return (
    <div className="flex h-full min-h-0 flex-col gap-3 overflow-y-auto scroll-thin">
      <div className="grid gap-3 xl:grid-cols-[320px_minmax(0,1fr)_330px]">
        <Panel title="Alert operations" bodyClassName="space-y-3 px-4 pb-4">
          <div className="grid grid-cols-3 gap-2">
            <Stat label="Critical" value={critical} tone="text-tier-critical" />
            <Stat label="Review" value={review} tone="text-tier-warning" />
            <Stat label="Total" value={events.length} tone="text-white" />
          </div>
          <div className={`rounded-xl border p-3 ${activeEvent ? 'border-tier-critical/30 bg-tier-critical/[0.06]' : 'border-tier-normal/20 bg-tier-normal/[0.04]'}`}>
            <div className="flex items-center justify-between gap-2"><span className={`text-[11px] font-bold uppercase tracking-wider ${activeEvent ? 'text-tier-critical' : 'text-tier-normal'}`}>{activeEvent ? 'Alert engine active' : 'Alert engine armed'}</span><span className="h-2 w-2 animate-soft-pulse rounded-full bg-current" /></div>
            <p className="mt-2 text-[11px] leading-relaxed text-slate-400">RainShield continuously evaluates ward risk. A critical threshold crossing creates an alert automatically; authority approval is required only before broadcast.</p>
          </div>
          {isSimulating && <div className="rounded-xl border border-accent/30 bg-accent/10 p-3 text-[11px] text-accent">Simulation is live. Risk transitions are being monitored automatically at the selected +{lead} min horizon.</div>}
          <p className="text-[10px] leading-relaxed text-slate-600">No “generate alert” step is required. Use the What-if simulator from the dashboard to inject a scenario and watch the alert engine react.</p>
        </Panel>

        <Panel title="Emergency alert preview" actions={<Segmented options={[{ id: 'operations', label: 'Operations' }, { id: 'cap', label: 'CAP 1.2' }]} value={tab} onChange={setTab} />} bodyClassName="space-y-3 px-4 pb-4">
          {preview && tab === 'operations' ? (
            <>
              <div className="rounded-xl border border-tier-critical/25 bg-gradient-to-br from-tier-critical/[0.08] to-transparent p-4">
                <div className="flex items-start justify-between gap-3"><div><p className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">{preview.areaDesc}</p><h3 className="mt-1 text-xl font-bold text-white">{preview.headline.replace(/^CRITICAL:\s*/i, '')}</h3></div><TierBadge tier={previewWard?.tier ?? 'NORMAL'} size="md" pulse={previewWard?.tier === 'CRITICAL'} /></div>
                <p className="mt-3 text-sm leading-relaxed text-slate-300">{preview.description}</p>
                <p className="mt-3 rounded-lg border border-tier-warning/20 bg-tier-warning/[0.05] px-3 py-2 text-xs text-tier-warning">{preview.instruction}</p>
              </div>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                <Kpi label="Probability" value={percent(previewWard?.peakFloodProbability ?? 0)} />
                <Kpi label="Depth" value={metres(previewWard?.peakWaterDepth ?? 0)} />
                <Kpi label="Lead time" value={duration(previewWard?.timeToInundation ?? null)} />
                <Kpi label="People" value={compactNumber(previewWard?.populationAtRisk ?? 0)} />
              </div>
              {activeEvent && <Workflow event={activeEvent} approve={approve} broadcast={broadcast} />}
            </>
          ) : preview ? (
            <pre className="max-h-[390px] overflow-auto rounded-xl bg-black/50 p-4 font-mono text-[10px] leading-relaxed text-slate-400 scroll-thin">{capToXml(preview)}</pre>
          ) : <Empty />}
        </Panel>

        <Panel title="Impact at a glance" bodyClassName="space-y-3 px-4 pb-4">
          <div className="rounded-xl border border-white/10 bg-white/[0.025] p-4"><p className="text-[10px] uppercase tracking-wider text-slate-500">People at risk</p><p className="mt-1 text-3xl font-bold tabular-nums text-white">{compactNumber(previewWard?.populationAtRisk ?? 0)}</p><p className="mt-1 text-[10px] text-slate-500">Targeted population estimate</p></div>
          <div className="grid grid-cols-2 gap-2">
            <Kpi label="Wards" value={String(wardSummaries.filter((w) => w.tier !== 'NORMAL').length)} />
            <Kpi label="Flooding cells" value={String(previewWard?.floodedCellCount ?? 0)} />
            <Kpi label="Max depth" value={metres(previewWard?.peakWaterDepth ?? 0)} />
            <Kpi label="Composite risk" value={(previewWard?.risk ?? 0).toFixed(2)} />
          </div>
          <div className="rounded-xl border border-white/10 bg-white/[0.025] p-3"><p className="text-[10px] uppercase tracking-wider text-slate-500">Risk drivers</p><div className="mt-2 space-y-2">{riskDrivers(previewWard).map((driver) => <div key={driver.label}><div className="flex justify-between text-[10px]"><span className="text-slate-400">{driver.label}</span><span className="font-semibold text-slate-200">{driver.value}</span></div><div className="mt-1 h-1.5 overflow-hidden rounded-full bg-white/[0.06]"><div className="h-full rounded-full bg-tier-critical" style={{ width: `${driver.percent}%` }} /></div></div>)}</div></div>
        </Panel>
      </div>

      <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_360px]">
        <Panel title="Alert event stream" bodyClassName="space-y-2 px-4 pb-4">
          {events.length === 0 ? <Empty text="No threshold crossings yet. RainShield is monitoring the grid." /> : events.map((event) => <EventCard key={event.id} event={event} />)}
        </Panel>
        <Panel title="Broadcast network" bodyClassName="space-y-2 px-4 pb-4">
          {CHANNELS.map(([label, detail, delivery]) => <div key={label} className="rounded-xl border border-white/10 bg-white/[0.02] p-3"><div className="flex justify-between"><div><p className="text-xs text-slate-200">{label}</p><p className="text-[10px] text-slate-500">{detail}</p></div><span className="text-[11px] font-semibold text-slate-300">{activeEvent?.status === 'ACTIVE' ? `${delivery}%` : 'Standby'}</span></div><div className="mt-2 h-1.5 overflow-hidden rounded-full bg-white/[0.06]"><div className="h-full rounded-full bg-accent transition-all duration-700" style={{ width: `${activeEvent?.status === 'ACTIVE' ? delivery : 0}%` }} /></div></div>)}
          <p className="pt-1 text-[10px] leading-relaxed text-slate-600">Prototype telemetry is simulated. Real telecom, siren and government gateways are not connected.</p>
        </Panel>
      </div>
    </div>
  );
}

function Stat({ label, value, tone }: { label: string; value: number; tone: string }) { return <div className="tile"><p className="text-[10px] text-slate-500">{label}</p><p className={`mt-1 text-xl font-bold tabular-nums ${tone}`}>{value}</p></div>; }
function Kpi({ label, value }: { label: string; value: string }) { return <div className="tile"><p className="text-[10px] text-slate-500">{label}</p><p className="mt-1 text-[14px] font-bold tabular-nums text-white">{value}</p></div>; }
function Empty({ text = 'No active alert.' }: { text?: string }) { return <div className="flex min-h-[120px] items-center justify-center rounded-xl border border-dashed border-white/10 text-center text-xs text-slate-600">{text}</div>; }
function EventCard({ event }: { event: ReturnType<typeof useAlertSystem>['events'][number] }) { return <div className="flex items-center justify-between gap-3 rounded-xl border border-white/10 bg-white/[0.02] p-3"><div><div className="flex items-center gap-2"><span className="h-2 w-2 rounded-full bg-tier-critical" /><p className="text-sm font-semibold text-white">{event.ward.ward.name}</p></div><p className="mt-1 text-[10px] text-slate-500">{new Date(event.createdAt).toLocaleTimeString('en-IN', { hour12: false })} · {event.reason[0]}</p></div><div className="text-right"><p className="text-[10px] font-bold uppercase text-tier-critical">{event.status.replace('_', ' ')}</p><p className="text-[10px] text-slate-500">{compactNumber(event.ward.populationAtRisk)} at risk</p></div></div>; }
function Workflow({ event, approve, broadcast }: { event: ReturnType<typeof useAlertSystem>['events'][number]; approve: (id: string) => void; broadcast: (id: string) => void }) { const steps = [['Detect', true], ['Draft', true], ['Review', event.status !== 'UNDER_REVIEW'], ['Broadcast', event.status === 'BROADCASTING' || event.status === 'ACTIVE'], ['Active', event.status === 'ACTIVE']] as const; return <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4"><div className="flex flex-wrap items-center gap-1.5">{steps.map(([label, done]) => <span key={label} className={`rounded-full px-2.5 py-1 text-[10px] font-semibold ${done ? 'bg-tier-normal/10 text-tier-normal' : 'bg-white/[0.05] text-slate-500'}`}>{done ? '✓ ' : ''}{label}</span>)}</div><div className="mt-3 flex gap-2">{event.status === 'UNDER_REVIEW' && <button className="btn btn-accent" onClick={() => approve(event.id)}>Approve alert</button>}{event.status === 'APPROVED' && <button className="btn btn-accent" onClick={() => broadcast(event.id)}>Approve & broadcast</button>}{event.status === 'ACTIVE' && <span className="rounded-full bg-tier-normal/10 px-3 py-1.5 text-[11px] font-semibold text-tier-normal">Broadcast active</span>}</div></div>; }
function riskDrivers(ward: ReturnType<typeof useDashboard>['wardSummaries'][number] | null) { if (!ward) return []; return [{ label: 'Flood probability', value: percent(ward.peakFloodProbability), percent: ward.peakFloodProbability * 100 }, { label: 'Expected depth', value: metres(ward.peakWaterDepth), percent: Math.min(100, ward.peakWaterDepth / 1.5 * 100) }, { label: 'Composite risk', value: ward.risk.toFixed(2), percent: ward.risk * 100 }]; }
