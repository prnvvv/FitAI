import { useAuth } from '../../context/AuthContext'
import { BrandMark } from '../BrandMark'
import { SuggestionList } from './SuggestionList'

interface WelcomeScreenProps {
  onSuggestion: (text: string) => void
}

export function WelcomeScreen({ onSuggestion }: WelcomeScreenProps) {
  const { user } = useAuth()
  const firstName = user?.displayName?.split(' ')[0] ?? 'there'

  return (
    <div className="welcome-screen">
      <div className="welcome-screen__mark">
        <BrandMark className="welcome-screen__mark-icon" />
      </div>
      <h1 className="welcome-screen__title">Hey, {firstName}. Ready to dive in?</h1>
      <p className="welcome-screen__subtitle">
        Ask about training, nutrition or recovery — or start from a suggestion.
      </p>
      <SuggestionList onSelect={onSuggestion} />
    </div>
  )
}
