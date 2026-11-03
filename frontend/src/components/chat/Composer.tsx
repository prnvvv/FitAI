import { ArrowUp, Loader2, Mic, MicOff, Paperclip, Square, X } from 'lucide-react'
import { useCallback, useEffect, useRef, useState, type KeyboardEvent, type ChangeEvent } from 'react'
import { useSpeechRecognition } from '../../hooks/useSpeechRecognition'
import { SPEECH_LANGUAGES } from '../../services/speechRecognition'

interface ComposerProps {
  /**
   * Text-only: the model cannot parse documents or images inline yet, so there
   * is no attachment picker. `onOpenDocuments` is the honest alternative — it
   * hands the user to the documents workflow that feeds the knowledge base.
   */
  onSend: (message: string) => void
  disabled?: boolean
  streaming?: boolean
  onStop?: () => void
  placeholder?: string
  onSpeechError?: (message: string) => void
  /** Opens the documents page. The control is hidden when not provided. */
  onOpenDocuments?: () => void
}

export function Composer({
  onSend,
  disabled,
  streaming,
  onStop,
  placeholder = 'Message FitAI...',
  onSpeechError,
  onOpenDocuments,
}: ComposerProps) {
  const [text, setText] = useState('')
  const [showUnsupported, setShowUnsupported] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  /** Mirrors `text` so several phrases arriving in one tick build on each other. */
  const textRef = useRef('')
  /**
   * Where dictated text goes. Clicking the microphone moves focus away from the
   * textarea, so the caret is captured up front; the first phrase replaces any
   * selection, later phrases continue after the previous one.
   */
  const caretRef = useRef<{ start: number; end: number } | null>(null)

  const updateText = useCallback((next: string) => {
    textRef.current = next
    setText(next)
  }, [])

  /** Inserts a finalised phrase at the caret without touching the rest of the draft. */
  const insertPhrase = useCallback(
    (phrase: string) => {
      const current = textRef.current
      const caret = caretRef.current
      const start = Math.min(caret ? caret.start : current.length, current.length)
      const end = Math.min(caret ? caret.end : start, current.length)
      const before = current.slice(0, start)
      const separator = before.length > 0 && !/\s$/.test(before) ? ' ' : ''
      const insertion = `${separator}${phrase}`
      const after = current.slice(end)
      updateText(`${before}${insertion}${after}`)
      const position = start + insertion.length
      caretRef.current = { start: position, end: position }
    },
    [updateText],
  )

  const speech = useSpeechRecognition({ onFinalText: insertPhrase, onError: onSpeechError })
  const { status: speechStatus } = speech

  /** Captures the caret, then starts listening. */
  const beginListening = useCallback(() => {
    const el = textareaRef.current
    caretRef.current = el
      ? { start: el.selectionStart ?? el.value.length, end: el.selectionEnd ?? el.value.length }
      : null
    speech.start()
  }, [speech])

  const requesting = speechStatus === 'requesting'
  const listening = speechStatus === 'listening'
  const finalizing = speechStatus === 'finalizing'
  const dictating = requesting || listening || finalizing
  // Sending while dictating would drop words that have not been finalised yet.
  const sendDisabled = !streaming && (!text.trim() || dictating)
  const multiLine = text.includes('\n') || text.length > 60

  const handleSend = () => {
    const trimmed = text.trim()
    if (!trimmed || disabled || dictating) return
    onSend(trimmed)
    updateText('')
    caretRef.current = null
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleChange = (e: ChangeEvent<HTMLTextAreaElement>) => {
    updateText(e.target.value)
    // Typing while dictating moves the insertion point with the user.
    if (caretRef.current) {
      const position = e.target.selectionStart ?? e.target.value.length
      caretRef.current = { start: position, end: position }
    }
  }

  // Keep the textarea height in step with its content, including dictated text.
  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = text ? `${Math.min(el.scrollHeight, 200)}px` : 'auto'
  }, [text])

  // After dictation finishes, hand focus to the textarea so the user can review
  // and edit before sending. Nothing is ever sent automatically.
  useEffect(() => {
    if (speechStatus !== 'completed') return
    const el = textareaRef.current
    if (!el) return
    el.focus()
    const position = caretRef.current?.end ?? el.value.length
    el.setSelectionRange(position, position)
  }, [speechStatus])

  const { error: speechError, dismissError: dismissSpeechError } = speech
  useEffect(() => {
    if (!speechError) return
    // Auto-dismiss so a stale error does not linger over the draft.
    const timer = setTimeout(dismissSpeechError, 10000)
    return () => clearTimeout(timer)
  }, [speechError, dismissSpeechError])

  useEffect(() => {
    if (!showUnsupported) return
    const timer = setTimeout(() => setShowUnsupported(false), 10000)
    return () => clearTimeout(timer)
  }, [showUnsupported])

  const statusLine = (() => {
    if (requesting) return 'Waiting for microphone permission…'
    if (listening) return speech.interim ? `Listening… ${speech.interim}` : 'Listening… speak now'
    if (finalizing) return 'Finalizing…'
    if (speechStatus === 'completed') return 'Added to your message. Review and edit it before sending.'
    return null
  })()

  return (
    <div className="composer">
      <div className={`composer__inner ${multiLine ? 'composer__inner--multi' : ''}`}>
        <div className="composer__tools">
          {onOpenDocuments && (
            <button
              type="button"
              className="composer__action"
              onClick={onOpenDocuments}
              disabled={disabled}
              aria-label="Add documents to the knowledge base"
              title="Manage documents"
            >
              <Paperclip size={18} />
            </button>
          )}
          <div className="composer__speech">
            {speechStatus === 'unsupported' ? (
              <button
                type="button"
                className="composer__mic composer__mic--unsupported"
                aria-disabled="true"
                aria-label="Voice input unavailable"
                title="Voice input is not available in this browser"
                onClick={() => setShowUnsupported(true)}
              >
                <MicOff size={18} />
              </button>
            ) : dictating ? (
              <>
                {requesting ? (
                  <span className="composer__mic" aria-hidden="true">
                    <Loader2 className="page__spinner" size={18} />
                  </span>
                ) : (
                  <button
                    type="button"
                    className="composer__mic composer__mic--recording"
                    onClick={speech.stop}
                    disabled={finalizing}
                    aria-label="Stop voice input"
                    title="Stop voice input"
                  >
                    {finalizing ? <Loader2 className="page__spinner" size={16} /> : <Square size={16} />}
                  </button>
                )}
                {listening && <span className="composer__recording-dot" aria-hidden="true" />}
                <button
                  type="button"
                  className="composer__mic composer__mic--cancel"
                  onClick={() => {
                    caretRef.current = null
                    speech.cancel()
                  }}
                  aria-label="Cancel voice input"
                  title="Cancel voice input (Esc)"
                >
                  <X size={16} />
                </button>
              </>
            ) : (
              <>
                <button
                  type="button"
                  className="composer__mic"
                  onClick={beginListening}
                  disabled={disabled}
                  aria-label="Start voice input"
                  title="Dictate a message"
                >
                  <Mic size={18} />
                </button>
                <select
                  className="composer__lang"
                  value={speech.language}
                  onChange={(e) => speech.setLanguage(e.target.value)}
                  aria-label="Voice input language"
                  title="Voice input language (availability depends on your browser)"
                >
                  {SPEECH_LANGUAGES.map((language) => (
                    <option key={language.code} value={language.code}>
                      {language.label}
                    </option>
                  ))}
                </select>
              </>
            )}
          </div>
        </div>
        <span className="composer__divider" aria-hidden="true" />
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
          disabled={streaming ? false : sendDisabled}
          className="composer__send"
          aria-label={streaming ? 'Stop generation' : 'Send message'}
        >
          {streaming ? <Square size={18} /> : <ArrowUp size={20} />}
        </button>
      </div>
      <p className="composer__speech-note" role="status" aria-live="polite">
        {statusLine}
      </p>
      {speechError && (
        <p className="composer__speech-error" role="alert">
          {speechError}
        </p>
      )}
      {showUnsupported && speech.unsupportedMessage && (
        <p className="composer__speech-error" role="alert">
          {speech.unsupportedMessage}
        </p>
      )}
    </div>
  )
}
