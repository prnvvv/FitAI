import { useEffect, useRef } from 'react'
import type { KeyboardEvent as ReactKeyboardEvent } from 'react'
import { CHIP_KEYS, metricLabel } from './metrics'
import type { MetricKey } from './metrics'

interface MetricChipsProps {
  value: MetricKey
  onChange: (metric: MetricKey) => void
}

/** Metric selector: role=tablist with roving tabindex and arrow-key movement. */
export function MetricChips({ value, onChange }: MetricChipsProps) {
  const refs = useRef<Array<HTMLButtonElement | null>>([])

  useEffect(() => {
    const index = CHIP_KEYS.indexOf(value)
    const chip = refs.current[index]
    // scrollIntoView is missing in jsdom; the guard keeps the effect a no-op there.
    if (typeof chip?.scrollIntoView === 'function') {
      chip.scrollIntoView({ block: 'nearest', inline: 'nearest' })
    }
  }, [value])

  const focusAt = (index: number) => {
    const next = (index + CHIP_KEYS.length) % CHIP_KEYS.length
    refs.current[next]?.focus()
    onChange(CHIP_KEYS[next])
  }

  const handleKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    const index = CHIP_KEYS.indexOf(value)
    if (event.key === 'ArrowRight') {
      event.preventDefault()
      focusAt(index + 1)
      return
    }
    if (event.key === 'ArrowLeft') {
      event.preventDefault()
      focusAt(index - 1)
      return
    }
    if (event.key === 'Home') {
      event.preventDefault()
      focusAt(0)
      return
    }
    if (event.key === 'End') {
      event.preventDefault()
      focusAt(CHIP_KEYS.length - 1)
    }
  }

  return (
    <div className="chips" role="tablist" aria-label="Metric" onKeyDown={handleKeyDown}>
      <div className="chips__scroller">
        {CHIP_KEYS.map((key, index) => (
          <span key={key} className={index === 6 ? 'chips__divider' : undefined}>
            <button
              ref={(el) => {
                refs.current[index] = el
              }}
              type="button"
              role="tab"
              aria-selected={key === value}
              tabIndex={key === value ? 0 : -1}
              title={key === 'bmi' ? 'Calculated from weight and height' : undefined}
              className={`chip${key === value ? ' chip--active' : ''}`}
              onClick={() => onChange(key)}
            >
              {metricLabel(key)}
            </button>
          </span>
        ))}
      </div>
    </div>
  )
}