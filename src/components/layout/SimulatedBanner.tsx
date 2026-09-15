import type { StormPhase } from '@/types';

/**
 * Says plainly that the region on screen is not real.
 *
 * The simulated region exists to exercise the Warning and Critical paths that a
 * quiet live region never reaches. That is only defensible if nobody can mistake
 * it for an observation, so this sits above the board wherever the simulated
 * region is selected — not tucked into a tooltip.
 */
export function SimulatedBanner({
  blurb,
  storm,
  compact = false,
}: {
  blurb?: string;
  storm?: StormPhase | null;
  compact?: boolean;
}) {
  return (
    <div
      className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-[12px] border
        border-amber-500/40 bg-amber-500/10 px-3 py-2"
      role="status"
    >
      <span className="rounded-full bg-amber-500/25 px-2 py-0.5 text-[10px] font-semibold
        uppercase tracking-wide text-amber-200">
        Simulated
      </span>

      <p className="text-[12px] font-medium text-amber-100">
        Generated storm over generated terrain — not a real place, not a measurement.
      </p>

      {storm && (
        <span className="text-[11px] text-amber-200/80">
          {Math.round(storm.phase * 100)}% through the landfall cycle · {storm.label}
        </span>
      )}

      {!compact && blurb && (
        <p className="w-full text-[11px] leading-relaxed text-amber-200/70">{blurb}</p>
      )}
    </div>
  );
}
