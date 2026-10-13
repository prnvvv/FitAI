import { Dumbbell, TrendingUp, Utensils } from 'lucide-react'

interface SuggestionListProps {
  onSelect: (text: string) => void
}

const SUGGESTIONS = [
  {
    id: 'workout-plan',
    text: 'Build me a 4-day workout plan',
    icon: Dumbbell,
  },
  {
    id: 'meal-plan',
    text: 'Plan high-protein meals for this week',
    icon: Utensils,
  },
  {
    id: 'progress-review',
    text: 'Review my progress and suggest next steps',
    icon: TrendingUp,
  },
]

export function SuggestionList({ onSelect }: SuggestionListProps) {
  return (
    <div className="suggestion-list">
      {SUGGESTIONS.map((suggestion) => (
        <button
          key={suggestion.id}
          type="button"
          className="suggestion-item"
          onClick={() => onSelect(suggestion.text)}
        >
          <suggestion.icon size={20} />
          <span>{suggestion.text}</span>
        </button>
      ))}
    </div>
  )
}
