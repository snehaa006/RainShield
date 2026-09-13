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
        <span className="text-[11px] text-slate-400">{label}</span>
        <span className="text-[13px] font-semibold tabular-nums text-white">{display}</span>
      </span>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
        className="h-1.5 w-full cursor-pointer appearance-none rounded-full
          [&::-moz-range-thumb]:h-4 [&::-moz-range-thumb]:w-4 [&::-moz-range-thumb]:rounded-full
          [&::-moz-range-thumb]:border-0 [&::-moz-range-thumb]:bg-white
          [&::-webkit-slider-thumb]:h-4 [&::-webkit-slider-thumb]:w-4
          [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:rounded-full
          [&::-webkit-slider-thumb]:bg-white
          [&::-webkit-slider-thumb]:shadow-[0_1px_3px_rgba(0,0,0,0.6)]"
        style={{
          backgroundImage: `linear-gradient(90deg, #0a84ff ${pct}%, rgba(255,255,255,0.10) ${pct}%)`,
        }}
      />
      {hint && <span className="block text-[11px] leading-snug text-slate-500">{hint}</span>}
    </label>
  );
}
