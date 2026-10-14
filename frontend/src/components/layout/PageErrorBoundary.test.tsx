import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { PageErrorBoundary } from './PageErrorBoundary'

function Boom({ shouldThrow }: { shouldThrow: boolean }) {
  if (shouldThrow) throw new TypeError('planned.filter is not a function')
  return <p>Plan content</p>
}

function Harness() {
  const [shouldThrow, setShouldThrow] = useState(true)
  return (
    <>
      <PageErrorBoundary name="Plan">
        <Boom shouldThrow={shouldThrow} />
      </PageErrorBoundary>
      <button type="button" onClick={() => setShouldThrow(false)}>
        Fix it
      </button>
    </>
  )
}

describe('PageErrorBoundary', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('replaces a crashing page with a calm message instead of a blank screen', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    render(<Harness />)

    expect(screen.getByRole('alert')).toHaveTextContent(/plan couldn't be displayed/i)
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()
    expect(spy).toHaveBeenCalled()
    const logged = spy.mock.calls
      .map((call) => call.map((arg) => (arg instanceof Error ? arg.message : String(arg))).join(' '))
      .join('\n')
    expect(logged).toContain('planned.filter is not a function')
  })

  it('shows the page again after Retry', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    const user = userEvent.setup()
    render(<Harness />)

    await user.click(screen.getByRole('button', { name: 'Fix it' }))
    await user.click(screen.getByRole('button', { name: 'Retry' }))

    expect(screen.getByText('Plan content')).toBeInTheDocument()
    expect(screen.queryByText(/couldn't be displayed/i)).not.toBeInTheDocument()
  })

  it('renders its children untouched when nothing throws', () => {
    render(
      <PageErrorBoundary name="Plan">
        <Boom shouldThrow={false} />
      </PageErrorBoundary>,
    )
    expect(screen.getByText('Plan content')).toBeInTheDocument()
  })
})