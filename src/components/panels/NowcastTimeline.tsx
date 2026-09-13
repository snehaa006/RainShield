import { LEAD_TIMES, LEAD_TIME_LABELS } from '@/lib/config';
import { clockAt } from '@/lib/format';
import { useDashboard } from '@/hooks/useDashboard';
import { HudCorners } from '@/components/ui/HudCorners';

/** Scrubber across the nowcasting model's forecast horizons. */
export function NowcastTimeline() {
  const { lead, setLead } = useDashboard();
  const activeIndex = LEAD_TIMES.indexOf(lead);

  return (
    <div className="panel flex items-center gap-5 px-4 py-3">
      <HudCorners />

      <div className="shrink-0">
        <p className="stat-label">Forecast horizon</p>
        <p className="font-display text-lg font-bold leading-tight text-cyan-100 neon-text">
          {LEAD_TIME_LABELS[lead]}
          <span className="ml-2 font-mono text-[10px] font-normal tracking-[0.14em] text-slate-500">
            {clockAt(lead)} IST
          </span>
        </p>
      </div>

      <span className="h-9 w-px shrink-0 bg-hud/25" />

      <div className="relative flex flex-1 items-center">
        <div className="absolute inset-x-0 h-px bg-surface-border" />
        <div
          className="absolute h-px bg-hud shadow-[0_0_10px_1px_rgba(34,211,238,0.8)]
            transition-[width] duration-300"
          style={{ width: `${(activeIndex / (LEAD_TIMES.length - 1)) * 100}%` }}
        />
        <div className="relative flex w-full justify-between">
          {LEAD_TIMES.map((value, index) => {
            const isActive = value === lead;
            const isPast = index <= activeIndex;
            return (
              <button
                key={value}
                type="button"
                onClick={() => setLead(value)}
                className="group flex flex-col items-center gap-1.5"
                aria-pressed={isActive}
              >
                {/* Diamond nodes read as instrument ticks rather than dots. */}
                <span
                  className={`h-2.5 w-2.5 rotate-45 border transition-all duration-200 ${
                    isActive
                      ? 'scale-[1.45] border-hud-bright bg-hud shadow-[0_0_12px_2px_rgba(34,211,238,0.9)]'
                      : isPast
                        ? 'border-hud/70 bg-hud-dim'
                        : 'border-slate-600 bg-surface-deep group-hover:border-hud/60'
                  }`}
                />
                <span
                  className={`font-mono text-[10px] uppercase tracking-[0.12em] transition-colors ${
                    isActive
                      ? 'font-semibold text-cyan-200 neon-text'
                      : 'text-slate-500 group-hover:text-slate-300'
                  }`}
                >
                  {LEAD_TIME_LABELS[value]}
                </span>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
