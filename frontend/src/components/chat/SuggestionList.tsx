import { Activity, Dumbbell, Salad, TrendingUp } from 'lucide-react'
import type { ReactNode } from 'react'

interface SuggestionListProps {
  onSelect: (text: string) => void
}

interface Suggestion {
  /** Two-line card copy: the leading line and its continuation. */
  label: string
  hint: string
  /** What is actually sent to the assistant. */
  prompt: string
  icon: ReactNode
}

const SUGGESTIONS: Suggestion[] = [
  {
    label: 'Help me plan my week',
    hint: 'A split that fits my schedule',
    prompt: 'Help me plan my week',
    icon: <Dumbbell size={18} />,
  },
  {
    label: 'What to eat',
    hint: 'After a late workout',
    prompt: 'What should I eat after a late workout?',
    icon: <Salad size={18} />,
  },
  {
    label: 'Explain progressive overload',
    hint: 'In plain terms',
    prompt: 'Explain progressive overload simply',
    icon: <Activity size={18} />,
  },
  {
    label: 'How is my progress?',
    hint: 'Weight and strength trends',
    prompt: 'How is my progress trending?',
    icon: <TrendingUp size={18} />,
  },
]

export function SuggestionList({ onSelect }: SuggestionListProps) {
  return (
    <div className="suggestion-list">
      {SUGGESTIONS.map((suggestion) => (
        <button
          key={suggestion.label}
          type="button"
          className="suggestion-item"
          onClick={() => onSelect(suggestion.prompt)}
        >
          <span className="suggestion-item__icon" aria-hidden="true">
            {suggestion.icon}
          </span>
          <span className="suggestion-item__label">{suggestion.label}</span>
          <span className="suggestion-item__hint">{suggestion.hint}</span>
        </button>
      ))}
    </div>
  )
}
