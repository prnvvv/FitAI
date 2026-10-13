import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { WelcomeScreen } from './WelcomeScreen'

describe('WelcomeScreen', () => {
  it('renders suggestions and triggers on select', () => {
    const onSuggestion = vi.fn()
    render(<WelcomeScreen onSuggestion={onSuggestion} />)

    const button = screen.getByRole('button', { name: /Build me a 4-day workout plan/i })
    fireEvent.click(button)

    expect(onSuggestion).toHaveBeenCalledWith('Build me a 4-day workout plan')
  })
})
