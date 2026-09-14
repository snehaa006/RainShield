import { FEED_LABELS } from '@/lib/config';
import { useDashboard } from '@/hooks/useDashboard';

/**
 * Tells the operator where the numbers on the map came from.
 *
 * This replaces the old scenario card: the board no longer replays canned
 * scenarios, it shows whatever the live feed and the model currently say, so
 * what matters is the provenance and freshness of that data.
 */
export function FeedNote() {
  const { feed, model, isSimulating, generatedAt } = useDashboard();

  if (!feed) return null;

  const label = FEED_LABELS[feed.source] ?? feed.source;
  const stale = feed.ageSeconds > feed.cacheTtl * 1.5;

  return (
    <div
      className="pointer-events-auto max-w-xs rounded-[12px] border border-surface-border
        bg-black/70 px-3 py-2 backdrop-blur-xl"
    >
      <p className="flex flex-wrap items-center gap-2 text-[12px] font-semibold text-white">
        <span
          className={`h-1.5 w-1.5 shrink-0 rounded-full ${
            feed.degraded || stale ? 'bg-tier-warning' : 'bg-tier-normal'
          }`}
        />
        {label}
        {isSimulating && (
          <span
            className="rounded-full bg-accent-soft px-2 py-0.5 text-[10px] font-medium text-accent"
          >
            Simulated
          </span>
        )}
        {feed.degraded && (
          <span
            className="rounded-full bg-amber-500/20 px-2 py-0.5 text-[10px] font-medium
              text-amber-300"
          >
            Degraded
          </span>
        )}
      </p>

      <p className="mt-1 text-[11px] leading-relaxed text-slate-400">
        {model?.loaded
          ? `${model.backend} · ${model.runtime}`
          : 'Analytical fallback — model weights unavailable'}
        {generatedAt && ` · scored ${new Date(generatedAt).toLocaleTimeString('en-GB', { hour12: false })}`}
      </p>

      {feed.degraded && feed.notes.length > 0 && (
        <p className="mt-1 text-[11px] leading-relaxed text-amber-300/80">{feed.notes.join(' · ')}</p>
      )}
    </div>
  );
}
