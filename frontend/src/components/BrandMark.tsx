import './BrandMark.css'

interface BrandMarkProps {
  /** Size/spacing hook for the call site; the mark scales with `font-size`. */
  className?: string
}

/**
 * The FitAI mark: five waveform bars suggesting a pulse. Decorative, so it is
 * hidden from assistive tech — the wordmark or button label carries the name.
 */
export function BrandMark({ className }: BrandMarkProps) {
  const classes = className ? `brand-mark ${className}` : 'brand-mark'

  return (
    <span className={classes} aria-hidden="true">
      <span className="brand-mark__bar" />
      <span className="brand-mark__bar" />
      <span className="brand-mark__bar" />
      <span className="brand-mark__bar" />
      <span className="brand-mark__bar" />
    </span>
  )
}
