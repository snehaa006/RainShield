interface MeterProps {
  label: string;
  /** 0-1 fill fraction. */
  value: number;
  display: string;
  color?: string;
  hint?: string;
}

export function Meter({ label, value, display, color = '#22d3ee', hint }: MeterProps) {
  const pct = Math.min(100, Math.max(0, value * 100));

  return (
    <div className="space-y-1.5">
      <div className="flex items-baseline justify-between gap-2">
        <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-slate-400">
          {label}
        </span>
        <span
          className="font-display text-[15px] font-bold tabular-nums"
          style={{ color, textShadow: `0 0 12px ${color}80` }}
        >
          {display}
        </span>
      </div>

      {/* Segmented track, like the gauges on the reference boards. */}
      <div
        className="relative h-2 overflow-hidden border border-surface-hairline bg-surface-deep/80"
        style={{
          backgroundImage:
            'repeating-linear-gradient(90deg, rgba(56,189,248,0.10) 0 3px, transparent 3px 6px)',
        }}
      >
        <div
          className="h-full transition-[width] duration-500"
          style={{
            width: `${pct}%`,
            background: `linear-gradient(90deg, ${color}66, ${color})`,
            boxShadow: `0 0 12px 0 ${color}`,
          }}
        />
      </div>
      {hint && <p className="text-[11px] leading-snug text-slate-500">{hint}</p>}
    </div>
  );
}
