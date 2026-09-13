import { useMemo, useState } from 'react';
import { buildCapAlert, capToXml } from '@/lib/cap';
import { useDashboard } from '@/hooks/useDashboard';
import { Panel } from '@/components/ui/Panel';

const CHANNELS = [
  { id: 'sms', label: 'SMS cell broadcast', detail: 'Telecom gateway' },
  { id: 'app', label: 'Mobile push', detail: 'Citizen app' },
  { id: 'siren', label: 'Siren activation', detail: 'Ward sirens' },
  { id: 'api', label: 'Authority API', detail: 'SDMA / NDMA' },
];

/** CAP payload preview plus the dissemination channels it would fan out to. */
export function CapPanel() {
  const { selectedWard, wardSummaries } = useDashboard();
  const [view, setView] = useState<'summary' | 'xml'>('summary');
  const ward = selectedWard ?? wardSummaries[0];

  const alert = useMemo(() => (ward ? buildCapAlert(ward) : null), [ward]);
  if (!alert) return null;

  return (
    <Panel
      title="CAP alerts"
      actions={
        <div className="flex gap-1">
          {(['summary', 'xml'] as const).map((option) => (
            <button
              key={option}
              type="button"
              onClick={() => setView(option)}
              className={`chip ${view === option ? 'chip-active' : ''}`}
            >
              {option === 'summary' ? 'Summary' : 'XML'}
            </button>
          ))}
        </div>
      }
      bodyClassName="min-h-0 flex-1 space-y-3 overflow-y-auto scroll-thin p-4"
    >
      {view === 'summary' ? (
        <>
          <p className="font-display text-base font-semibold tracking-wide text-cyan-50">
            {alert.headline}
          </p>
          <p className="text-xs leading-relaxed text-slate-400">{alert.description}</p>
          <p className="clip-bevel border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs
            leading-relaxed text-amber-200">
            {alert.instruction}
          </p>
          <dl className="grid grid-cols-3 gap-2 text-[11px]">
            {[
              ['Severity', alert.severity],
              ['Urgency', alert.urgency],
              ['Certainty', alert.certainty],
            ].map(([label, value]) => (
              <div key={label}>
                <dt className="stat-label">{label}</dt>
                <dd className="text-slate-300">{value}</dd>
              </div>
            ))}
          </dl>
        </>
      ) : (
        <pre className="clip-bevel overflow-x-auto border border-surface-hairline
          bg-surface-deep/80 p-3 font-mono text-[10px]
          leading-relaxed text-slate-400 scroll-thin">
          {capToXml(alert)}
        </pre>
      )}

      <div className="space-y-1.5 border-t border-surface-hairline pt-3">
        {CHANNELS.map((channel) => (
          <div
            key={channel.id}
            className="clip-bevel flex items-center justify-between border
              border-surface-hairline bg-surface-deep/60 px-3 py-1.5"
          >
            <div>
              <p className="text-xs text-slate-300">{channel.label}</p>
              <p className="font-mono text-[10px] tracking-wide text-slate-500">{channel.detail}</p>
            </div>
            <span className="border border-slate-700 px-2 py-0.5 font-mono text-[9px] uppercase
              tracking-[0.14em] text-slate-500">
              Not wired
            </span>
          </div>
        ))}
      </div>
    </Panel>
  );
}
