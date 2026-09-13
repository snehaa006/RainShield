import { LEAD_TIMES, LEAD_TIME_LABELS } from '@/lib/config';
import { clockAt } from '@/lib/format';
import { useDashboard } from '@/hooks/useDashboard';

/** Scrubber across the nowcasting model's forecast horizons. */
export function NowcastTimeline() {
  const { lead, setLead } = useDashboard();

  return (
    <div className="panel flex flex-wrap items-center justify-between gap-3 px-4 py-2.5">
      <div>
        <p className="text-[11px] text-slate-500">Forecast horizon</p>
        <p className="text-[15px] font-semibold leading-tight text-white">
          {LEAD_TIME_LABELS[lead]}
          <span className="ml-2 text-[11px] font-normal text-slate-500">{clockAt(lead)} IST</span>
        </p>
      </div>

      <div className="segmented">
        {LEAD_TIMES.map((value) => (
          <button
            key={value}
            type="button"
            onClick={() => setLead(value)}
            aria-pressed={value === lead}
            className={`segmented-item ${value === lead ? 'segmented-item-active' : ''}`}
          >
            {LEAD_TIME_LABELS[value]}
          </button>
        ))}
      </div>
    </div>
  );
}
