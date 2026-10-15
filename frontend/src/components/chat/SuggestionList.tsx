import { Dumbbell, Salad, Sparkles, TrendingUp } from 'lucide-react'
import type { ReactNode } from 'react'

interface SuggestionListProps {
  onSelect: (text: string) => void
}

interface Suggestion {
  /** Card title; also the message sent when the card is chosen. */
  title: string
  subtitle: string
  icon: ReactNode
  tone: 'blue' | 'amber' | 'mint' | 'lavender'
}

const SUGGESTIONS: Suggestion[] = [
  {
    title: 'Create a workout plan',
    subtitle: 'Based on my goals.',
    icon: <Dumbbell size={18} />,
    tone: 'blue',
  },
  {
    title: 'What should I eat?',
    subtitle: 'For better recovery.',
    icon: <Salad size={18} />,
    tone: 'amber',
  },
  {
    title: 'Analyse my progress',
    subtitle: 'From my data.',
    icon: <TrendingUp size={18} />,
    tone: 'mint',
  },
  {
    title: 'General fitness advice',
    subtitle: 'Ask anything.',
    icon: <Sparkles size={18} />,
    tone: 'lavender',
  },
]

export function SuggestionList({ onSelect }: SuggestionListProps) {
  return (
    <div className="suggestion-list">
      {SUGGESTIONS.map((suggestion) => (
        <button
          key={suggestion.title}
          type="button"
          className="suggestion-item"
          data-tone={suggestion.tone}
          onClick={() => onSelect(suggestion.title)}
        >
          <span className="suggestion-item__icon" aria-hidden="true">
            {suggestion.icon}
          </span>
          <span className="suggestion-item__body">
            <span className="suggestion-item__title">{suggestion.title}</span>
            <span className="suggestion-item__subtitle">{suggestion.subtitle}</span>
          </span>
        </button>
      ))}
    </div>
  )
}
