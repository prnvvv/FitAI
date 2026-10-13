interface SuggestionListProps {
  onSelect: (text: string) => void
}

const SUGGESTIONS = [
  'Help me plan my week',
  'What should I eat after a late workout?',
  'Explain progressive overload simply',
]

export function SuggestionList({ onSelect }: SuggestionListProps) {
  return (
    <div className="suggestion-list">
      {SUGGESTIONS.map((text) => (
        <button
          key={text}
          type="button"
          className="suggestion-item"
          onClick={() => onSelect(text)}
        >
          <span>{text}</span>
        </button>
      ))}
    </div>
  )
}
