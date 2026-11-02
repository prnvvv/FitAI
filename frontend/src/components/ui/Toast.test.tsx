import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ToastProvider, useToast } from './Toast'

function Trigger() {
  const toast = useToast()
  return <button onClick={() => toast.show('Failed to save workout', 'error')}>go</button>
}

describe('Toast', () => {
  it('shows an error toast as an alert and can be dismissed', () => {
    render(
      <ToastProvider>
        <Trigger />
      </ToastProvider>,
    )
    fireEvent.click(screen.getByText('go'))
    expect(screen.getByRole('alert')).toHaveTextContent('Failed to save workout')
    fireEvent.click(screen.getByLabelText('Dismiss'))
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('is a harmless no-op without a provider', () => {
    render(<Trigger />)
    fireEvent.click(screen.getByText('go'))
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})
