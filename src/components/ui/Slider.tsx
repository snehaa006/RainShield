interface SliderProps {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  display: string;
  onChange: (value: number) => void;
  hint?: string;
}

export function Slider({ label, value, min, max, step, display, onChange, hint }: SliderProps) {
  const pct = ((value - min) / (max - min)) * 100;

  return (
    <label className="block space-y-2">
      <span className="flex items-baseline justify-between gap-2">
        <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-slate-400">
          {label}
        </span>
        <span className="font-display text-[15px] font-bold tabular-nums text-cyan-200 neon-text">
          {display}
        </span>
      </span>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
        className="h-1.5 w-full cursor-pointer appearance-none bg-surface-deep
          [&::-moz-range-thumb]:h-3.5 [&::-moz-range-thumb]:w-3.5 [&::-moz-range-thumb]:rounded-full
          [&::-moz-range-thumb]:border-0 [&::-moz-range-thumb]:bg-hud-bright
          [&::-webkit-slider-thumb]:h-3.5 [&::-webkit-slider-thumb]:w-3.5
          [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:rounded-full
          [&::-webkit-slider-thumb]:bg-hud-bright
          [&::-webkit-slider-thumb]:shadow-[0_0_10px_2px_rgba(34,211,238,0.8)]"
        style={{
          backgroundImage: `linear-gradient(90deg, #0e7490 0%, #22d3ee ${pct}%, rgba(10,21,36,0.9) ${pct}%)`,
        }}
      />
      {hint && <span className="block text-[11px] leading-snug text-slate-500">{hint}</span>}
    </label>
  );
}
