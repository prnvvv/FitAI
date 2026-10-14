import { Sparkles, Dumbbell, UtensilsCrossed, BarChart2, HelpCircle } from 'lucide-react'
import { useAuth } from '../../context/AuthContext'
import { useProfile } from '../../hooks/useProfile'
import { SuggestionList } from './SuggestionList'

interface WelcomeScreenProps {
  onSuggestion: (text: string) => void
}

export function WelcomeScreen({ onSuggestion }: WelcomeScreenProps) {
  const { user } = useAuth()
  const { profile } = useProfile()
  const firstName = user?.displayName?.split(' ')[0] ?? 'there'

  const goal = profile?.goal
  const activityLevel = profile?.activity_level

  const suggestions = [
    { text: 'Create a workout plan for this week', icon: Dumbbell },
    { text: 'What should I eat after a late workout?', icon: UtensilsCrossed },
    { text: 'Analyze my progress from the last month', icon: BarChart2 },
    { text: 'Explain progressive overload simply', icon: HelpCircle },
  ]

  return (
    <div className="welcome-screen">
      <div className="welcome-screen__icon">
        <Sparkles size={40} />
      </div>
      <h1 className="welcome-screen__title">
        Hi, {firstName}. Ready to work toward your goals?
      </h1>
      {goal && (
        <p className="welcome-screen__subtitle">
          Your goal: <strong>{goal}</strong>
          {activityLevel && ` • Activity: ${activityLevel.replace('_', ' ')}`}
        </p>
      )}
      <SuggestionList suggestions={suggestions} onSelect={onSuggestion} />
    </div>
  )
}