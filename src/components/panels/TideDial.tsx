/**
 * Sea level against the astronomical range, as a bar rather than a number.
 *
 * The useful thing to see at a glance is not the level itself but where it
 * sits between lowest and highest astronomical tide, and which way it is
 * going — because that is what decides whether the gravity outfalls are open.
 */

import type { TideState } from '@/types';

const PHASE_LABELS: Record<TideState['phase'], string> = {
  high: 'High water',
  low: 'Low water',
  flooding: 'Flooding',
  ebbing: 'Ebbing',
};

export function TideDial({ tide, overridden }: { tide: TideState; overridden: boolean }) {
  const pct = Math.min(100, Math.max(0, tide.normalised * 100));
  const mslPct = Math.min(
    100,
    Math.max(
      0,
      ((tide.meanSeaLevelMCd - tide.lowestAstronomicalMCd) /
        (tide.highestAstronomicalMCd - tide.lowestAstronomicalMCd)) *
        100,
    ),
  );

  return (
    <div className="space-y-2">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-[13px] font-semibold text-white">
          {PHASE_LABELS[tide.phase]}
          {overridden && <span className="ml-1.5 text-[11px] text-amber-300">pinned</span>}
        </span>
        <span className="text-[15px] font-semibold tabular-nums text-white">
          {tide.levelMCd.toFixed(2)} m
        </span>
      </div>

      <div className="relative h-2.5 overflow-hidden rounded-full bg-white/[0.08]">
        <div
          className="h-full rounded-full bg-gradient-to-r from-sky-700 to-sky-400
            transition-[width] duration-500"
          style={{ width: `${pct}%` }}
        />
        {/* Mean sea level, so the bar has a reference and not just a length. */}
        <div
          className="absolute inset-y-0 w-px bg-white/40"
          style={{ left: `${mslPct}%` }}
          title="Mean sea level"
        />
      </div>

      <div className="flex justify-between text-[10px] tabular-nums text-slate-500">
        <span>LAT {tide.lowestAstronomicalMCd.toFixed(1)}</span>
        <span>
          {overridden
            ? 'level pinned — no rate'
            : `${tide.rateMPerHr >= 0 ? '+' : ''}${tide.rateMPerHr.toFixed(2)} m/hr`}
        </span>
        <span>HAT {tide.highestAstronomicalMCd.toFixed(1)}</span>
      </div>

      <p className="text-[11px] text-slate-500">
        Spring range {tide.springRangeM.toFixed(1)} m, above chart datum.
      </p>
    </div>
  );
}
