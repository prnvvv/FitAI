import { ArrowUp, Square } from 'lucide-react'
import { useRef, useState, type KeyboardEvent, type ChangeEvent } from 'react'

interface ComposerProps {
  /**
   * Text-only for now: the model cannot parse documents or images inline, so
   * there is no attachment picker yet. Files are still uploaded from the
   * Documents page and used through the knowledge base.
   */
  onSend: (message: string) => void
  disabled?: boolean
  streaming?: boolean
  onStop?: () => void
  placeholder?: string
}

export function Composer({
  onSend,
  disabled,
  streaming,
  onStop,
  placeholder = 'Ask anything',
}: ComposerProps) {
  const [text, setText] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const handleSend = () => {
    const trimmed = text.trim()
    if (!trimmed || disabled) return
    onSend(trimmed)
    setText('')
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
    }
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleChange = (e: ChangeEvent<HTMLTextAreaElement>) => {
    setText(e.target.value)
    const el = e.target
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`
  }

  const multiLine = text.split('\n').length > 1 || text.length > 60

  return (
    <div className="composer">
      <div className={`composer__inner ${multiLine ? 'composer__inner--multi' : ''}`}>
        <textarea
          ref={textareaRef}
          rows={1}
          value={text}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={disabled}
          aria-label="Message"
          className="composer__input"
        />
        <button
          type="button"
          onClick={streaming ? onStop : handleSend}
          disabled={!streaming && !text.trim()}
          className="composer__send"
          aria-label={streaming ? 'Stop generation' : 'Send message'}
        >
          {streaming ? <Square size={18} /> : <ArrowUp size={20} />}
        </button>
      </div>
    </div>
  )
}