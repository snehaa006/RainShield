interface SwitchProps {
  checked: boolean;
  onChange: () => void;
  label: string;
}

/** iOS toggle switch. */
export function Switch({ checked, onChange, label }: SwitchProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={onChange}
      className="flex items-center gap-2 text-[11px] font-medium text-slate-300"
    >
      {label}
      <span
        className={`relative h-[18px] w-8 rounded-full transition-colors duration-200 ${
          checked ? 'bg-tier-normal' : 'bg-white/15'
        }`}
      >
        <span
          className={`absolute top-[2px] h-[14px] w-[14px] rounded-full bg-white shadow-control
            transition-transform duration-200 ${checked ? 'translate-x-[16px]' : 'translate-x-[2px]'}`}
        />
      </span>
    </button>
  );
}
