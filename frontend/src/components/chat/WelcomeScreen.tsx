import { Sparkles } from 'lucide-react'
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
      <div className="welcome-screen__icon">
        <Sparkles size={40} />
      </div>
      <h1 className="welcome-screen__title">Hey, {firstName}. Ready to dive in?</h1>
      <SuggestionList onSelect={onSuggestion} />
    </div>
  )
}
