/** Compact single-choice control built on native radios (free arrow-key support). */
export interface SegmentedOption {
  value: string
  label: string
}

interface SegmentedControlProps {
  /** Accessible name for the group. */
  label: string
  /** Radio group name; must be unique per page. */
  name: string
  options: SegmentedOption[]
  value: string
  onChange: (value: string) => void
}

export function SegmentedControl({ label, name, options, value, onChange }: SegmentedControlProps) {
  return (
    <div role="radiogroup" aria-label={label} className="plan__segmented">
      {options.map((option) => (
        <label key={option.value} className="plan__segmented-option">
          <input
            type="radio"
            name={name}
            value={option.value}
            checked={value === option.value}
            onChange={() => onChange(option.value)}
          />
          <span>{option.label}</span>
        </label>
      ))}
    </div>
  )
}
