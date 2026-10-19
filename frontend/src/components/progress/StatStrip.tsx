interface StatStripProps {
  latest: number | null
  change: number | null
  rangeLabel: string
  entries: number
  unit: string
  latestDate: string | null
  /** Per-metric display precision, reused from the chart helpers. */
  format: (value: number) => string
  loading?: boolean
}

/** Four inline cells separated by hairlines; Latest is the primary number. */
export function StatStrip({
  latest,
  change,
  rangeLabel,
  entries,
  unit,
  latestDate,
  format,
  loading,
}: StatStripProps) {
  if (loading) {
    return (
      <div className="stat-strip" aria-hidden="true">
        {[0, 1, 2, 3].map((index) => (
          <div key={index} className="stat">
            <div className="skeleton skeleton--label" />
            <div className="skeleton skeleton--value" />
          </div>
        ))}
      </div>
    )
  }

  const rangeText =
    rangeLabel === '—'
      ? '—'
      : `${rangeLabel.includes('–') ? rangeLabel.split('–').map((part) => format(Number(part))).join('–') : format(Number(rangeLabel))}${unit ? ` ${unit}` : ''}`

  return (
    <div className="stat-strip">
      <div className="stat stat--primary">
        <span className="stat__label">Latest</span>
        <span className="stat__value stat__value--large">
          {latest === null ? '—' : format(latest)}
          {latest !== null && unit && <span className="stat__unit"> {unit}</span>}
        </span>
        <span className="stat__caption">{latestDate}</span>
      </div>
      <div className="stat">
        <span className="stat__label">Change</span>
        <span className="stat__value">
          {change !== null
            ? `${change > 0 ? '+' : ''}${format(change)}${unit ? ` ${unit}` : ''}`
            : '—'}
        </span>
      </div>
      <div className="stat">
        <span className="stat__label">Range</span>
        <span className="stat__value">{rangeText}</span>
      </div>
      <div className="stat">
        <span className="stat__label">Entries</span>
        <span className="stat__value">{entries}</span>
      </div>
    </div>
  )
}