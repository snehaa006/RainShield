interface SegmentedProps<T extends string> {
  options: { id: T; label: string }[];
  value: T;
  onChange: (value: T) => void;
  className?: string;
}

/** iOS-style segmented control: one soft track, the active item lifted. */
export function Segmented<T extends string>({
  options,
  value,
  onChange,
  className = '',
}: SegmentedProps<T>) {
  return (
    <div className={`segmented ${className}`} role="tablist">
      {options.map((option) => (
        <button
          key={option.id}
          type="button"
          role="tab"
          aria-selected={option.id === value}
          onClick={() => onChange(option.id)}
          className={`segmented-item ${option.id === value ? 'segmented-item-active' : ''}`}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
