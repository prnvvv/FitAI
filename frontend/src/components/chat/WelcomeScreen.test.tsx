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
  it('renders greeting and triggers on select', () => {
    const onSuggestion = vi.fn()
    renderWelcome(onSuggestion)
    expect(screen.getByRole('heading')).toHaveTextContent('Ready to dive in?')
    const button = screen.getByRole('button', { name: /Help me plan my week/i })
    fireEvent.click(button)
    expect(onSuggestion).toHaveBeenCalledWith('Help me plan my week')
  })
})
