import { useEffect, useState } from 'react';
import { REGION, SCENARIOS } from '@/lib/config';
import { useDashboard } from '@/hooks/useDashboard';
import { TierBadge } from '@/components/ui/TierBadge';

/**
 * Command-bar header: a clipped centre title plate flanked by system telemetry,
 * in the style of an operations big-board.
 */
export function Header() {
  const { scenario, setScenarioId, regionSummary } = useDashboard();

  return (
    <header className="relative z-20 shrink-0">
      {/* Angled backdrop plate behind the whole bar. */}
      <div className="absolute inset-0 border-b border-hud/25 bg-gradient-to-b
        from-[#0b1c30]/95 via-[#071426]/90 to-transparent backdrop-blur-md" />
      <div className="pointer-events-none absolute inset-x-0 bottom-0 h-px bg-gradient-to-r
        from-transparent via-hud/70 to-transparent" />

      <div className="relative flex items-center justify-between gap-4 px-5 py-2.5">
        {/* Identity */}
        <div className="flex shrink-0 items-center gap-3">
          <div className="relative flex h-10 w-10 items-center justify-center">
            <span className="absolute inset-0 rounded-full border border-hud/40" />
            <span className="absolute inset-0 animate-hud-spin rounded-full border border-dashed
              border-hud/50" />
            <span className="absolute inset-1.5 rounded-full bg-hud/10 shadow-hud-glow" />
            <span className="relative text-lg text-cyan-200 neon-text">☂</span>
          </div>
          <div>
            <h1 className="flex items-center font-display text-base font-bold uppercase
              tracking-[0.22em] text-cyan-50 neon-text">
              RainShield
              <span className="ml-1.5 text-hud">AI</span>
              <span className="ml-2 border border-hud/40 bg-hud/10 px-1.5 py-px font-mono
                text-[9px] font-medium uppercase tracking-[0.2em] text-hud">
                Prototype
              </span>
            </h1>
            <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-slate-500">
              {REGION.name} · {REGION.state} · 1 km grid
            </p>
          </div>
        </div>

        {/* Centre plate — absolutely centred so it stays on the board's axis. */}
        <div className="pointer-events-none absolute left-1/2 hidden -translate-x-1/2
          items-center gap-3 min-[1700px]:flex">
          <span className="h-px w-16 bg-gradient-to-r from-transparent to-hud/60" />
          <div className="clip-plate border-x border-t border-hud/40 bg-hud/10 px-7 py-1.5">
            <p className="font-display text-sm font-semibold uppercase tracking-[0.34em]
              text-cyan-100 neon-text">
              Flood Command &amp; Early Warning
            </p>
          </div>
          <span className="h-px w-16 bg-gradient-to-l from-transparent to-hud/60" />
        </div>

        {/* Telemetry */}
        <div className="flex shrink-0 items-center gap-4">
          <label className="flex items-center gap-2 font-mono text-[10px] uppercase
            tracking-[0.16em] text-slate-500">
            Scenario
            <select
              value={scenario.id}
              onChange={(event) => setScenarioId(event.target.value)}
              className="clip-bevel border border-hud/30 bg-surface-solid/80 px-2 py-1.5
                font-sans text-xs normal-case tracking-normal text-cyan-100 outline-none
                transition-colors hover:border-hud/60 focus:border-hud"
            >
              {SCENARIOS.map((option) => (
                <option key={option.id} value={option.id} className="bg-surface-solid">
                  {option.isHistorical ? `↺ ${option.name}` : option.name}
                </option>
              ))}
            </select>
          </label>
          <Clock />
          <TierBadge tier={regionSummary.tier} size="md" pulse={regionSummary.tier !== 'NORMAL'} />
        </div>
      </div>
    </header>
  );
}

/** Live wall-clock readout, as every operations board carries. */
function Clock() {
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(id);
  }, []);

  return (
    <div className="hidden text-right md:block">
      <p className="font-display text-lg font-bold leading-none tabular-nums text-cyan-100
        neon-text">
        {now.toLocaleTimeString('en-GB', { hour12: false })}
      </p>
      <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-slate-500">
        {now.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })} IST
      </p>
    </div>
  );
}
