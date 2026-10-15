import { ArrowUp, Paperclip, Square } from 'lucide-react'
import { useRef, useState, type KeyboardEvent, type ChangeEvent } from 'react'

interface ComposerProps {
  onSend: (message: string, files: File[]) => void
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
  placeholder = 'Ask anything about fitness...',
}: ComposerProps) {
  const [text, setText] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const handleSend = () => {
    const trimmed = text.trim()
    if (!trimmed || disabled) return
    onSend(trimmed, files)
    setText('')
    setFiles([])
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

  const handleFileSelect = (e: ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      setFiles((prev) => [...prev, ...Array.from(e.target.files!)])
    }
    e.target.value = ''
  }

  const multiLine = text.split('\n').length > 1 || text.length > 60

  return (
    <div className="composer">
      {files.length > 0 && (
        <div className="composer__files">
          {files.map((file, idx) => (
            <div key={`${file.name}-${idx}`} className="composer__file-chip">
              <span>{file.name}</span>
              <button
                type="button"
                onClick={() => setFiles((prev) => prev.filter((_, i) => i !== idx))}
                aria-label={`Remove ${file.name}`}
              >
                ×
              </button>
            </div>
          ))}
        </div>
      )}
      <div className={`composer__inner ${multiLine ? 'composer__inner--multi' : ''}`}>
        <label className="composer__attach" aria-label="Attach document">
          <Paperclip size={20} />
          <input type="file" accept=".pdf,.txt,.docx" multiple onChange={handleFileSelect} />
        </label>
        <textarea
          ref={textareaRef}
          rows={1}
          value={text}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={disabled}
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
