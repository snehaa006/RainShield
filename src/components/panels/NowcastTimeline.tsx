import { LEAD_TIMES, LEAD_TIME_LABELS } from '@/lib/config';
import { clockAt } from '@/lib/format';
import { useDashboard } from '@/hooks/useDashboard';

/** Scrubber across the nowcasting model's forecast horizons. */
export function NowcastTimeline() {
  const { lead, setLead } = useDashboard();
  const activeIndex = LEAD_TIMES.indexOf(lead);

  return (
    <div className="flex items-center gap-4 rounded-xl border border-surface-border
      bg-surface-raised px-4 py-3">
      <div className="shrink-0">
        <p className="stat-label">Forecast horizon</p>
        <p className="text-sm font-semibold text-slate-100">
          {LEAD_TIME_LABELS[lead]}
          <span className="ml-2 text-xs font-normal text-slate-500">{clockAt(lead)} IST</span>
        </p>
      </div>

      <div className="relative flex flex-1 items-center">
        <div className="absolute inset-x-0 h-px bg-surface-border" />
        <div
          className="absolute h-px bg-sky-500 transition-[width] duration-300"
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
                <span
                  className={`h-2.5 w-2.5 rounded-full border transition-colors ${
                    isActive
                      ? 'scale-125 border-sky-300 bg-sky-400'
                      : isPast
                        ? 'border-sky-600 bg-sky-700'
                        : 'border-slate-600 bg-surface group-hover:border-slate-400'
                  }`}
                />
                <span
                  className={`text-[11px] transition-colors ${
                    isActive ? 'font-semibold text-sky-300' : 'text-slate-500 group-hover:text-slate-300'
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
