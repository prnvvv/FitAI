import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { AuthProvider } from '../../context/AuthContext'
import { WelcomeScreen } from './WelcomeScreen'

function renderWelcome(onSuggestion = vi.fn()) {
  return render(
    <AuthProvider>
      <WelcomeScreen onSuggestion={onSuggestion} />
    </AuthProvider>,
  )
}

describe('WelcomeScreen', () => {
  it('renders the greeting and triggers on select', () => {
    const onSuggestion = vi.fn()
    renderWelcome(onSuggestion)
    expect(screen.getByRole('heading')).toHaveTextContent('Hi there')
    expect(screen.getByText('How can I help with your fitness today?')).toBeInTheDocument()
    const button = screen.getByRole('button', { name: /Create a workout plan/i })
    fireEvent.click(button)
    expect(onSuggestion).toHaveBeenCalledWith('Create a workout plan')
  })
})
