import { useAuth } from '../../context/AuthContext'
import { SuggestionList } from './SuggestionList'

interface WelcomeScreenProps {
  onSuggestion: (text: string) => void
}

export function WelcomeScreen({ onSuggestion }: WelcomeScreenProps) {
  const { user } = useAuth()
  const firstName = user?.displayName?.split(' ')[0] ?? 'there'

  return (
    <div className="welcome-screen">
      <h1 className="welcome-screen__title">Hi {firstName}</h1>
      <p className="welcome-screen__subtitle">How can I help with your fitness today?</p>
      <SuggestionList onSelect={onSuggestion} />
    </div>
  )
}
