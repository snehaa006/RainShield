/**
 * Which hazard path is serving, and — on the physics path — how well it closed.
 *
 * Mass closure is worth a panel because it is the one claim here that can be
 * checked rather than trusted. It is the governing equation integrated over
 * the whole domain and the whole run: rain in, minus everything that left,
 * minus what is still standing. A solver that conserves mass by construction
 * closes to floating-point noise, and saying so with the number attached is
 * more convincing than saying "physics-informed".
 */

import { useDashboard } from '@/hooks/useDashboard';
import { Panel } from '@/components/ui/Panel';
import type { SolverStatus } from '@/types';

export function SolverPanel({ className = '' }: { className?: string }) {
  const { solver } = useDashboard();
  if (!solver) return null;

  return (
    <Panel
      title="Hazard model"
      className={className}
      actions={
        <span
          className="rounded-full px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide"
          style={
            solver.massConserving
              ? { background: 'rgba(34,197,94,0.15)', color: '#4ade80' }
              : { background: 'rgba(148,163,184,0.15)', color: '#94a3b8' }
          }
        >
          {solver.mode}
        </span>
      }
    >
      <p className="text-[13px] font-medium text-white">{solver.label}</p>
      <p className="mt-1 text-[11px] leading-relaxed text-slate-400">{solver.note}</p>

      {solver.massClosure ? (
        <MassBalance closure={solver.massClosure} solver={solver} />
      ) : (
        <p className="mt-3 rounded-lg bg-white/[0.04] px-3 py-2 text-[11px] leading-relaxed text-slate-500">
          No mass balance to report: this path evaluates a response curve per
          cell, so there is no conserved quantity to close.
        </p>
      )}
    </Panel>
  );
}

function MassBalance({
  closure,
  solver,
}: {
  closure: NonNullable<SolverStatus['massClosure']>;
  solver: SolverStatus;
}) {
  const rows: [string, number][] = [
    ['Rainfall in', closure.rainfallM3],
    ['Discharged to sea', closure.toSeaM3],
    ['Pumped', closure.pumpedM3],
    ['Storm drains', closure.drainedM3],
    ['Infiltrated', closure.infiltratedM3],
    ['Left the domain', closure.offDomainM3],
    ['Still standing', closure.storedM3],
  ];

  return (
    <div className="mt-3 space-y-3">
      <div className="rounded-lg bg-emerald-500/[0.08] px-3 py-2">
        <div className="text-[10px] uppercase tracking-wide text-emerald-300/70">
          Mass balance closed to
        </div>
        <div className="text-[17px] font-semibold tabular-nums text-emerald-300">
          {formatClosure(closure.error)}
        </div>
        <div className="mt-0.5 text-[10px] text-slate-500">
          {closure.residualM3.toExponential(1)} m³ unaccounted of{' '}
          {millions(closure.rainfallM3)} that fell
          {solver.steps ? ` · ${solver.steps} steps` : ''}
          {solver.elapsedMs ? ` · ${solver.elapsedMs.toFixed(0)} ms` : ''}
        </div>
      </div>

      <dl className="space-y-1">
        {rows.map(([label, value]) => (
          <div key={label} className="flex items-baseline justify-between gap-2">
            <dt className="text-[11px] text-slate-400">{label}</dt>
            <dd className="text-[11px] tabular-nums text-slate-200">{millions(value)}</dd>
          </div>
        ))}
      </dl>

      {solver.notes?.map((note) => (
        <p key={note} className="text-[11px] text-amber-300">
          {note}
        </p>
      ))}
    </div>
  );
}

/** Closure is normally ~1e-15, so a percentage would just read "0.00%". */
function formatClosure(error: number): string {
  if (error === 0) return 'exactly 0';
  if (error < 1e-9) return `${error.toExponential(1)} (machine precision)`;
  return `${(error * 100).toFixed(4)}%`;
}

function millions(m3: number): string {
  if (Math.abs(m3) >= 1e6) return `${(m3 / 1e6).toFixed(2)} Mm³`;
  if (Math.abs(m3) >= 1e3) return `${(m3 / 1e3).toFixed(1)} km³×10⁻³`;
  return `${m3.toFixed(0)} m³`;
}
