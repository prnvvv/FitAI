import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { restoreChartWidth, stubChartWidth } from '../../test/chartGeometry'
import { gapThreshold, ProgressChart, xTicks, yDomain } from './ProgressChart'
import type { SeriesPoint } from './metrics'

const day = (offset: number, hour = 8) => {
  const date = new Date()
  date.setDate(date.getDate() - offset)
  date.setHours(hour, 0, 0, 0)
  return date.toISOString()
}

const point = (id: string, value: number, at: string, notes: string | null = null): SeriesPoint => ({
  id,
  value,
  measured_at: at,
  unit: 'kg',
  notes,
})

const renderChart = (
  points: SeriesPoint[],
  overrides: Partial<Parameters<typeof ProgressChart>[0]> = {},
  width = 800,
) => {
  stubChartWidth(width)
  const user = userEvent.setup()
  render(
    <ProgressChart
      points={points}
      metric="weight"
      units="metric"
      range="30d"
      height={240}
      showAllAvailable={false}
      onShowAll={() => {}}
      onLog={() => {}}
      {...overrides}
    />,
  )
  return { user }
}

const cx = (element: Element | undefined) => Number(element?.getAttribute('cx'))

beforeEach(() => {
  stubChartWidth()
})

afterEach(() => {
  restoreChartWidth()
})

describe('ProgressChart geometry helpers', () => {
  it('pads the y domain by 10% of the span', () => {
    expect(yDomain([70, 80])).toEqual({ min: 69, max: 81 })
  })

  it('keeps a flat series inside a sensible minimum span', () => {
    const domain = yDomain([70, 70, 70])
    expect(domain.max - domain.min).toBeCloseTo(7, 5)
    expect((domain.min + domain.max) / 2).toBe(70)
  })

  it('flags a gap larger than three times the median interval', () => {
    const base = new Date('2026-01-01T08:00:00').getTime()
    const day = 86_400_000
    const times = [base, base + day, base + 2 * day, base + 14 * day]
    expect(gapThreshold(times)).toBe(3 * day)
    expect(gapThreshold([base])).toBe(Number.POSITIVE_INFINITY)
  })

  it('picks daily, weekly and monthly ticks from the plotted span', () => {
    const from = new Date('2026-10-01T00:00:00').getTime()
    const to = new Date('2026-10-07T00:00:00').getTime()
    expect(xTicks('7d', from, to).every((tick) => tick.label.length === 3)).toBe(true)
    expect(xTicks('30d', from, new Date('2026-10-28T00:00:00').getTime())).toHaveLength(4)
    expect(xTicks('90d', from, new Date('2026-12-20T00:00:00').getTime()).at(-1)?.label).toMatch(/Dec/)
  })
})

describe('ProgressChart', () => {
  it('shows an empty state with no chart for zero entries', () => {
    renderChart([])
    expect(screen.getByText('No weight entries in this range.')).toBeInTheDocument()
    expect(document.querySelector('svg')).toBeNull()
    expect(screen.getByRole('button', { name: 'Log weight' })).toBeInTheDocument()
  })

  it('offers "Show all" when entries exist outside the range', async () => {
    let shown = false
    renderChart([], { showAllAvailable: true, onShowAll: () => (shown = true) })
    screen.getByRole('button', { name: 'Show all' }).click()
    expect(shown).toBe(true)
  })

  it('draws one centred dot for a single entry, with no line or axis', () => {
    renderChart([point('a', 70, day(1))])
    expect(screen.getByRole('img', { name: /One entry: 70.0 kg/ })).toBeInTheDocument()
    expect(document.querySelectorAll('.chart__line')).toHaveLength(0)
    expect(document.querySelectorAll('.chart__grid')).toHaveLength(0)
    const dot = document.querySelector('.chart--single circle:not([data-testid])') as SVGCircleElement
    expect(Number(dot.getAttribute('cx'))).toBe(400)
    expect(Number(dot.getAttribute('cy'))).toBe(80)
    expect(dot.getAttribute('r')).toBe('6')
  })

  it('draws a line with markers for two points and places them by time', () => {
    renderChart([point('a', 80, day(10)), point('b', 70, day(2))])
    const markers = document.querySelectorAll('.chart__marker')
    expect(markers).toHaveLength(2)
    // Time-proportional: the older point sits left of the newer one, spread
    // across the plot width and never at the extremes.
    expect(cx(markers[0])).toBeLessThan(cx(markers[1]))
    expect(cx(markers[0])).toBeGreaterThanOrEqual(46)
    expect(cx(markers[1])).toBeLessThanOrEqual(800 - 14)
    expect(document.querySelectorAll('.chart__line')).toHaveLength(1)
  })

  it('places the third point proportionally between the first two', () => {
    renderChart([point('a', 80, day(10)), point('b', 75, day(4)), point('c', 70, day(2))])
    const [first, middle, last] = document.querySelectorAll('.chart__marker')
    const span = cx(last) - cx(first)
    // 6 of 8 days elapsed: the middle point is 75% across the domain.
    expect((cx(middle) - cx(first)) / span).toBeCloseTo(0.75, 2)
  })

  it('dashes a segment that spans a missing-data gap', () => {
    renderChart([
      point('a', 81, day(30)),
      point('b', 80, day(28)),
      point('c', 79, day(26)),
      point('d', 70, day(1)),
    ])
    const lines = document.querySelectorAll('.chart__line')
    expect(lines).toHaveLength(3)
    expect(lines[0].getAttribute('class')).not.toContain('dashed')
    expect(lines[1].getAttribute('class')).not.toContain('dashed')
    expect(lines[2].getAttribute('class')).toContain('dashed')
  })

  it('draws only the latest marker when there are more than 40 points', () => {
    const points = Array.from({ length: 50 }, (_, index) =>
      point(`p${index}`, 70 + index / 10, day(50 - index)),
    )
    renderChart(points)
    const markers = document.querySelectorAll('.chart__marker')
    expect(markers).toHaveLength(1)
    expect(markers[0].getAttribute('class')).toContain('chart__marker--latest')
  })

  it('renders four gridlines and round x ticks for many points', () => {
    const points = Array.from({ length: 20 }, (_, index) => point(`p${index}`, 70 + index, day(20 - index)))
    renderChart(points, { range: '7d' })
    expect(document.querySelectorAll('.chart__grid')).toHaveLength(4)
    expect(document.querySelectorAll('.chart__tick-label').length).toBeGreaterThan(1)
    expect(document.querySelectorAll('.chart__axis-label')[0].textContent).toContain('kg')
  })

  it('keeps the dot a circle at several container sizes', () => {
    const points = [point('a', 80, day(5)), point('b', 72, day(1))]
    for (const width of [320, 640, 1200]) {
      cleanup()
      stubChartWidth(width)
      const view = render(
        <ProgressChart
          points={points}
          metric="weight"
          units="metric"
          range="30d"
          height={240}
          showAllAvailable={false}
          onShowAll={() => {}}
          onLog={() => {}}
        />,
      )
      view.rerender(
        <ProgressChart
          points={points}
          metric="weight"
          units="metric"
          range="30d"
          height={240}
          showAllAvailable={false}
          onShowAll={() => {}}
          onLog={() => {}}
        />,
      )
      const svg = document.querySelector('.chart__svg') as SVGSVGElement
      // Pixel coordinates: the svg is drawn at exactly the measured size, so no
      // uniform or non-uniform scaling can distort the marker or the text.
      expect(Number(svg.getAttribute('width'))).toBe(width)
      expect(Number(svg.getAttribute('height'))).toBe(240)
      expect(svg.getAttribute('viewBox')).toBeNull()
      expect(svg.getAttribute('preserveAspectRatio')).toBeNull()
    }
    cleanup()
  })

  it('formats values per metric and honours the unit toggle', () => {
    renderChart(
      [
        { ...point('a', 70, day(3)), unit: 'lb' },
        { ...point('b', 72, day(1)), unit: 'lb' },
      ],
      { units: 'imperial' },
    )
    expect(screen.getByRole('img', { name: /entries from 154\.3 to 158\.7 lb/ })).toBeInTheDocument()
  })

  it('renders steps as bars when there are 31 or fewer points', () => {
    const points = Array.from({ length: 10 }, (_, index) =>
      point(`s${index}`, 10000 + index * 100, day(10 - index)),
    )
    renderChart(points, { metric: 'steps' })
    expect(document.querySelectorAll('.chart__bar')).toHaveLength(10)
    expect(document.querySelectorAll('.chart__line')).toHaveLength(0)
    expect(screen.getByRole('img', { name: /10 entries from 10,000 to 10,900/ })).toBeInTheDocument()
  })

  it('moves the active point with the arrow keys and shows a tooltip', async () => {
    const { user } = renderChart([
      point('a', 80, day(5)),
      point('b', 75, day(3)),
      point('c', 70, day(1)),
    ])
    const chart = screen.getByRole('img', { name: /Weight chart/ })
    chart.focus()
    await user.keyboard('{ArrowRight}')
    expect(screen.getByRole('status').textContent).toMatch(/80\.0/)
    await user.keyboard('{ArrowRight}')
    expect(screen.getByRole('status').textContent).toMatch(/75\.0/)
    await user.keyboard('{ArrowLeft}')
    expect(screen.getByRole('status').textContent).toMatch(/80\.0/)
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('includes the note in the tooltip', async () => {
    const { user } = renderChart([point('a', 80, day(5), 'after long run'), point('b', 75, day(1))])
    const chart = screen.getByRole('img', { name: /Weight chart/ })
    chart.focus()
    await user.keyboard('{ArrowRight}')
    expect(screen.getByRole('status')).toHaveTextContent('after long run')
  })

  it('never invents points: markers equal the number of entries', () => {
    const points = Array.from({ length: 5 }, (_, index) => point(`p${index}`, 70 + index, day(30 - index * 6)))
    renderChart(points)
    expect(document.querySelectorAll('.chart__marker')).toHaveLength(points.length)
  })
})