import { useEffect, useState } from 'react';
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
  const { regionSummary, feed, isUpdating, refresh, region, regions, regionId, setRegionId } =
    useDashboard();

  return (
    <header className="shrink-0 border-b border-surface-border bg-surface-deep">
      <div className="flex flex-wrap items-center gap-x-6 gap-y-3 px-5 py-3">
        <div className="shrink-0">
          <h1 className="text-[17px] font-semibold leading-tight tracking-tight text-white">
            RainShield AI
          </h1>
          <p className="text-[11px] text-slate-500">
            Flood early warning · {region ? `${region.name}, ${region.state}` : 'loading region…'}
          </p>
        </div>

        {regions.length > 1 && (
          <label className="flex shrink-0 items-center gap-2 text-[11px] text-slate-500">
            <span className="sr-only">Region</span>
            <select
              value={regionId}
              onChange={(event) => setRegionId(event.target.value)}
              className="rounded-[10px] border border-surface-border bg-white/[0.04] px-2.5 py-1.5
                text-[12px] text-slate-200 outline-none transition-colors hover:bg-white/[0.08]
                focus:border-accent"
            >
              {regions.map((item) => (
                <option key={item.id} value={item.id} className="bg-surface-deep text-slate-200">
                  {item.name}
                </option>
              ))}
            </select>
          </label>
        )}

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
          <Clock timezone={region?.timezone} />
          <TierBadge tier={regionSummary.tier} size="md" pulse={regionSummary.tier !== 'NORMAL'} />
        </div>
      </div>
    </header>
  );
}

/**
 * Wall-clock readout in the *region's* zone.
 *
 * This used to render the browser's local time and label it IST regardless of
 * where the browser actually was, so an operator outside India read a time that
 * was hours off under a label saying otherwise. Formatting explicitly in the
 * region's zone makes the label true, and shows the zone it is true for.
 */
function Clock({ timezone }: { timezone?: string }) {
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(id);
  }, []);

  const zone = timezone ?? 'Asia/Kolkata';
  const time = now.toLocaleTimeString('en-GB', { hour12: false, timeZone: zone });
  const date = now.toLocaleDateString('en-GB', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    timeZone: zone,
  });
  // "GMT+5:30" is what Intl gives without a short name; either is honest.
  const label =
    new Intl.DateTimeFormat('en-GB', { timeZone: zone, timeZoneName: 'short' })
      .formatToParts(now)
      .find((part) => part.type === 'timeZoneName')?.value ?? zone;

  return (
    <div className="hidden text-right md:block" title={zone}>
      <p className="text-[13px] font-semibold leading-none tabular-nums text-white">{time}</p>
      <p className="mt-0.5 text-[10px] text-slate-500">
        {date} {label}
      </p>
    </div>
  );
}
