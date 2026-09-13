interface MeterProps {
  label: string;
  /** 0-1 fill fraction. */
  value: number;
  display: string;
  color?: string;
  hint?: string;
}

export function Meter({ label, value, display, color = '#0a84ff', hint }: MeterProps) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-[11px] text-slate-400">{label}</span>
        <span className="text-[13px] font-semibold tabular-nums text-white">{display}</span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-white/[0.08]">
        <div
          className="h-full rounded-full transition-[width] duration-500"
          style={{
            width: `${Math.min(100, Math.max(0, value * 100))}%`,
            backgroundColor: color,
          }}
        />
      </div>
      {hint && <p className="text-[11px] leading-snug text-slate-500">{hint}</p>}
    </div>
  );
}
