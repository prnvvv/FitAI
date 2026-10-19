/**
 * jsdom has no layout: every element reports clientWidth 0 and ResizeObserver is
 * undefined. The chart measures its container before drawing, so tests stub both
 * to render real pixel geometry.
 */

let restore: (() => void) | null = null

export function stubChartWidth(width = 800): void {
  restore?.()
  const original = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'clientWidth')
  Object.defineProperty(HTMLElement.prototype, 'clientWidth', {
    configurable: true,
    get() {
      return this.classList?.contains('chart') ? width : 0
    },
  })
  const originalRO = globalThis.ResizeObserver
  if (typeof globalThis.ResizeObserver === 'undefined') {
    class NoopResizeObserver {
      observe(): void {}
      unobserve(): void {}
      disconnect(): void {}
    }
    globalThis.ResizeObserver = NoopResizeObserver as unknown as typeof ResizeObserver
  }
  restore = () => {
    if (original) Object.defineProperty(HTMLElement.prototype, 'clientWidth', original)
    else delete (HTMLElement.prototype as unknown as Record<string, unknown>).clientWidth
    if (typeof originalRO === 'undefined') delete (globalThis as { ResizeObserver?: unknown }).ResizeObserver
    restore = null
  }
}

export function restoreChartWidth(): void {
  restore?.()
}