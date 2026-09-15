import { useMemo, useState } from 'react';
import { buildCapAlert, capToXml } from '@/lib/cap';
import { useDashboard } from '@/hooks/useDashboard';
import { Panel } from '@/components/ui/Panel';
import { Segmented } from '@/components/ui/Segmented';

const CHANNELS = [
  { id: 'sms', label: 'SMS cell broadcast', detail: 'Telecom gateway' },
  { id: 'app', label: 'Mobile push', detail: 'Citizen app' },
  { id: 'siren', label: 'Siren activation', detail: 'Ward sirens' },
  { id: 'api', label: 'Authority API', detail: 'SDMA / NDMA' },
];

/** CAP payload preview plus the dissemination channels it would fan out to. */
export function CapPanel({ className = '' }: { className?: string }) {
  const { selectedWard, wardSummaries, region } = useDashboard();
  const [view, setView] = useState<'summary' | 'xml'>('summary');
  const ward = selectedWard ?? wardSummaries[0];

  const alert = useMemo(() => (ward ? buildCapAlert(ward, region) : null), [ward, region]);
  if (!alert) return null;

  return (
    <Panel
      title="CAP alerts"
      className={className}
      actions={
        <Segmented
          options={[
            { id: 'summary', label: 'Summary' },
            { id: 'xml', label: 'CAP XML' },
          ]}
          value={view}
          onChange={setView}
        />
      }
      bodyClassName="min-h-0 flex-1 space-y-3 overflow-y-auto scroll-thin px-4 pb-4"
    >
      {view === 'summary' ? (
        <>
          <p className="text-[15px] font-semibold leading-snug text-white">{alert.headline}</p>
          <p className="text-[12px] leading-relaxed text-slate-400">{alert.description}</p>
          <p className="rounded-[10px] bg-tier-warning/10 px-3 py-2 text-[12px] leading-relaxed
            text-tier-warning">
            {alert.instruction}
          </p>
          <dl className="grid grid-cols-3 gap-2 text-[11px]">
            {[
              ['Severity', alert.severity],
              ['Urgency', alert.urgency],
              ['Certainty', alert.certainty],
            ].map(([label, value]) => (
              <div key={label}>
                <dt className="text-[10px] text-slate-500">{label}</dt>
                <dd className="text-[12px] text-slate-200">{value}</dd>
              </div>
            ))}
          </dl>
        </>
      ) : (
        <pre className="overflow-x-auto rounded-[10px] bg-black/60 p-3 font-mono text-[10px]
          leading-relaxed text-slate-400 scroll-thin">
          {capToXml(alert)}
        </pre>
      )}

      <div className="space-y-1.5 border-t border-surface-hairline pt-3">
        {CHANNELS.map((channel) => (
          <div
            key={channel.id}
            className="flex items-center justify-between rounded-[10px] bg-white/[0.03]
              px-3 py-2"
          >
            <div>
              <p className="text-[12px] text-slate-200">{channel.label}</p>
              <p className="text-[10px] text-slate-500">{channel.detail}</p>
            </div>
            <span className="rounded-full bg-white/[0.06] px-2 py-0.5 text-[10px] text-slate-500">
              Not wired
            </span>
          </div>
        ))}
      </div>
    </Panel>
  );
}
