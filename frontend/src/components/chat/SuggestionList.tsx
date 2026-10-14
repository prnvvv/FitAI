import { type ComponentType } from 'react'

interface Suggestion {
  text: string
  icon: ComponentType<{ size?: number }>
}

interface SuggestionListProps {
  suggestions: Suggestion[]
  onSelect: (text: string) => void
}

export function SuggestionList({ suggestions, onSelect }: SuggestionListProps) {
  return (
    <div className="suggestion-list">
      {suggestions.map(({ text, icon: Icon }) => (
        <button
          key={text}
          type="button"
          className="suggestion-item"
          onClick={() => onSelect(text)}
        >
          <Icon size={20} aria-hidden="true" />
          <span>{text}</span>
        </button>
      ))}
    </div>
  )
}