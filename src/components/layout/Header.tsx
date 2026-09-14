import { useEffect, useState } from 'react';
import { REGION } from '@/lib/config';
import { useDashboard } from '@/hooks/useDashboard';
import { TierBadge } from '@/components/ui/TierBadge';
import type { ViewId } from '@/views';
import { VIEWS } from '@/views';

interface HeaderProps {
  view: ViewId;
  onViewChange: (view: ViewId) => void;
}

/** Product title, primary view tabs and live status. */
export function Header({ view, onViewChange }: HeaderProps) {
  const { regionSummary, feed, isUpdating, refresh } = useDashboard();

  return (
    <header className="shrink-0 border-b border-surface-border bg-surface-deep">
      <div className="flex flex-wrap items-center gap-x-6 gap-y-3 px-5 py-3">
        <div className="shrink-0">
          <h1 className="text-[17px] font-semibold leading-tight tracking-tight text-white">
            RainShield AI
          </h1>
          <p className="text-[11px] text-slate-500">
            Flood early warning · {REGION.name}, {REGION.state}
          </p>
        </div>

        <nav className="order-last flex w-full items-center gap-1 overflow-x-auto scroll-thin
          lg:order-none lg:w-auto lg:flex-1 lg:justify-center">
          {VIEWS.map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => onViewChange(item.id)}
              className={`shrink-0 rounded-[10px] px-3 py-1.5 text-[12px] font-medium
                transition-colors ${
                  view === item.id
                    ? 'bg-accent-soft text-accent'
                    : 'text-slate-400 hover:bg-white/[0.06] hover:text-slate-200'
                }`}
            >
              {item.label}
            </button>
          ))}
        </nav>

        <div className="ml-auto flex shrink-0 items-center gap-3">
          <button
            type="button"
            onClick={refresh}
            disabled={isUpdating}
            title={
              feed
                ? `Feed: ${feed.source}, ${Math.round(feed.ageSeconds)}s old. Click to re-pull.`
                : 'Re-pull the live feed'
            }
            className="flex items-center gap-2 rounded-[10px] border border-surface-border
              bg-white/[0.04] px-2.5 py-1.5 text-[12px] text-slate-200 outline-none
              transition-colors hover:bg-white/[0.08] focus:border-accent
              disabled:cursor-not-allowed disabled:opacity-60"
          >
            <span
              className={`h-1.5 w-1.5 rounded-full ${
                isUpdating
                  ? 'animate-pulse bg-accent'
                  : feed?.degraded
                    ? 'bg-tier-warning'
                    : 'bg-tier-normal'
              }`}
            />
            {isUpdating ? 'Updating' : 'Live'}
          </button>
          <Clock />
          <TierBadge tier={regionSummary.tier} size="md" pulse={regionSummary.tier !== 'NORMAL'} />
        </div>
      </div>
    </header>
  );
}

/** Live wall-clock readout. */
function Clock() {
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(id);
  }, []);

  return (
    <div className="hidden text-right md:block">
      <p className="text-[13px] font-semibold leading-none tabular-nums text-white">
        {now.toLocaleTimeString('en-GB', { hour12: false })}
      </p>
      <p className="mt-0.5 text-[10px] text-slate-500">
        {now.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })} IST
      </p>
    </div>
  );
}
