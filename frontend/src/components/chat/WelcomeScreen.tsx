import { Sparkles } from 'lucide-react'
import { SuggestionList } from './SuggestionList'

interface WelcomeScreenProps {
  onSuggestion: (text: string) => void
}

export function WelcomeScreen({ onSuggestion }: WelcomeScreenProps) {
  return (
    <div className="welcome-screen">
      <div className="welcome-screen__icon">
        <Sparkles size={40} />
      </div>
      <h1 className="welcome-screen__title">What can I help with?</h1>
      <p className="welcome-screen__subtitle">
        Ask about workouts, nutrition, recovery, or track your fitness progress.
      </p>
      <SuggestionList onSelect={onSuggestion} />
    </div>
  )
}
