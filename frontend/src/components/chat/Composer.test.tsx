import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { Composer } from './Composer'

describe('Composer', () => {
  it('renders placeholder and sends message on Enter', () => {
    const onSend = vi.fn()
    render(<Composer onSend={onSend} />)

    const input = screen.getByPlaceholderText('Ask anything about fitness...')
    fireEvent.change(input, { target: { value: 'Hello' } })
    fireEvent.keyDown(input, { key: 'Enter' })

    expect(onSend).toHaveBeenCalledWith('Hello', [])
  })

  it('does not send empty messages', () => {
    const onSend = vi.fn()
    render(<Composer onSend={onSend} />)

    const button = screen.getByLabelText('Send message')
    expect(button).toBeDisabled()

    fireEvent.click(button)
    expect(onSend).not.toHaveBeenCalled()
  })
})
