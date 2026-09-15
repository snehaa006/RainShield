import { useEffect, useState } from 'react';
import { compactNumber, duration, metres, percent } from '@/lib/format';
import type { AlertEvent } from '@/hooks/useAlertSystem';

export function EmergencyAlertOverlay({ event, onReview, onDismiss }: { event: AlertEvent; onReview: () => void; onDismiss: () => void }) {
  const [seconds, setSeconds] = useState(12);
  useEffect(() => {
    const timer = window.setInterval(() => setSeconds((value) => Math.max(0, value - 1)), 1000);
    return () => window.clearInterval(timer);
  }, []);

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/75 p-4 backdrop-blur-sm" role="alertdialog" aria-modal="true">
      <div className="emergency-overlay w-full max-w-3xl overflow-hidden rounded-2xl border border-tier-critical/60 bg-[#0d0f12] shadow-2xl">
        <div className="critical-stripe" />
        <div className="p-5 sm:p-7">
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.16em] text-tier-critical"><span className="h-2.5 w-2.5 animate-soft-pulse rounded-full bg-tier-critical" />Critical flood event detected automatically</div>
              <h2 className="mt-2 text-2xl font-bold tracking-tight text-white sm:text-3xl">{event.ward.ward.name}</h2>
              <p className="mt-1 text-sm text-slate-400">{event.cap.areaDesc}</p>
            </div>
            <div className="rounded-full bg-tier-critical/15 px-3 py-1 text-xs font-bold text-tier-critical">CRITICAL</div>
          </div>

          <div className="mt-6 grid grid-cols-2 gap-2 sm:grid-cols-4">
            <Metric label="Flood probability" value={percent(event.ward.peakFloodProbability)} />
            <Metric label="Expected depth" value={metres(event.ward.peakWaterDepth)} />
            <Metric label="Lead time" value={duration(event.ward.timeToInundation)} />
            <Metric label="People at risk" value={compactNumber(event.ward.populationAtRisk)} />
          </div>

          <div className="mt-3 grid gap-3 sm:grid-cols-[1.4fr_1fr]">
            <div className="rounded-xl border border-white/10 bg-white/[0.035] p-4">
              <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">Why RainShield triggered this</p>
              <div className="mt-3 space-y-2">{event.reason.map((reason) => <p key={reason} className="flex gap-2 text-sm text-slate-200"><span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-tier-critical" />{reason}</p>)}</div>
            </div>
            <div className="rounded-xl border border-white/10 bg-white/[0.035] p-4">
              <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">AI recommendation</p>
              <p className="mt-2 text-sm font-semibold text-white">Prepare a critical public warning for authority review.</p>
              <p className="mt-2 text-xs leading-relaxed text-slate-500">The alert is already drafted. Human approval is required before simulated dissemination.</p>
            </div>
          </div>

          <div className="mt-5 flex flex-col-reverse gap-2 sm:flex-row sm:items-center sm:justify-between">
            <button type="button" className="btn" onClick={onDismiss}>Dismiss {seconds > 0 ? `(${seconds})` : ''}</button>
            <button type="button" className="btn btn-accent !rounded-lg !px-5 !py-2.5 text-xs font-bold" onClick={onReview}>Review alert →</button>
          </div>
        </div>
      </div>
    </div>
  );
}
function Metric({ label, value }: { label: string; value: string }) {
  return <div className="rounded-xl border border-white/10 bg-white/[0.035] p-3"><p className="text-[10px] text-slate-500">{label}</p><p className="mt-1 text-lg font-bold tabular-nums text-white">{value}</p></div>;
}
