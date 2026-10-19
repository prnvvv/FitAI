import { ArrowUp, Loader2, Mic, Paperclip, Square, X } from 'lucide-react'
import { useCallback, useEffect, useRef, useState, type KeyboardEvent, type ChangeEvent } from 'react'
import { useSpeechToText, type SpeechToText } from '../../hooks/useSpeechToText'

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
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  /**
   * Where the caret sat when recording started. Clicking the microphone moves
   * focus away from the textarea, so the position is captured up front and the
   * transcript is inserted back where the user was typing.
   */
  const caretRef = useRef<{ start: number; end: number } | null>(null)

  /**
   * Inserts the recognised text where the caret was, keeping any existing draft
   * and focusing the input so the user can correct it before sending.
   */
  const insertTranscript = useCallback((transcript: string) => {
    const el = textareaRef.current
    if (!el) {
      setText((current) => (current ? `${current} ${transcript}` : transcript))
      return
    }
    const caret = caretRef.current
    const start = caret ? caret.start : (el.selectionStart ?? el.value.length)
    const end = caret ? caret.end : (el.selectionEnd ?? el.value.length)
    caretRef.current = null
    const separator = start > 0 && !/\s$/.test(el.value.slice(0, start)) ? ' ' : ''
    const insertion = `${separator}${transcript}`
    const next = `${el.value.slice(0, start)}${insertion}${el.value.slice(end)}`
    setText(next)
    el.focus()
    const caretPosition = start + insertion.length
    requestAnimationFrame(() => el.setSelectionRange(caretPosition, caretPosition))
  }, [])

  const handleTranscript = useCallback(
    (transcript: string) => insertTranscript(transcript),
    [insertTranscript],
  )

  const speech: SpeechToText = useSpeechToText({
    onTranscript: handleTranscript,
    onError: onSpeechError,
  })

  /** Captures the caret, then starts recording. */
  const beginRecording = useCallback(() => {
    const el = textareaRef.current
    caretRef.current = el
      ? { start: el.selectionStart ?? el.value.length, end: el.selectionEnd ?? el.value.length }
      : null
    void speech.start()
  }, [speech])

  const recording = speech.status === 'recording'
  const transcribing = speech.status === 'transcribing'
  // Sending while recording would lose the clip; transcription must finish first.
  const sendDisabled = !streaming && (!text.trim() || recording)
  const multiLine = text.split('\n').length > 1 || text.length > 60
  const hasTools = Boolean(onOpenDocuments) || speech.isSupported

  const handleSend = () => {
    const trimmed = text.trim()
    if (!trimmed || disabled || recording) return
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

  /** Escape cancels a recording wherever focus sits inside the composer. */
  const handleComposerKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key !== 'Escape' || !recording) return
    e.preventDefault()
    speech.cancel()
  }

  const handleChange = (e: ChangeEvent<HTMLTextAreaElement>) => {
    setText(e.target.value)
    const el = e.target
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`
  }

  const speechError = speech.error
  const dismissSpeechError = speech.dismissError

  useEffect(() => {
    if (!speechError) return
    // Auto-dismiss so a stale permission error does not linger over the draft.
    const timer = setTimeout(dismissSpeechError, 8000)
    return () => clearTimeout(timer)
  }, [speechError, dismissSpeechError])

  return (
    <div className="composer" onKeyDown={handleComposerKeyDown}>
      <div className={`composer__inner ${multiLine ? 'composer__inner--multi' : ''}`}>
        {hasTools && (
          <>
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
              {speech.isSupported && (
                <div className="composer__speech">
                  {recording ? (
                    <>
                      <button
                        type="button"
                        className="composer__mic composer__mic--recording"
                        onClick={speech.stop}
                        disabled={transcribing}
                        aria-label="Stop recording and transcribe"
                        title="Stop recording"
                      >
                        <Square size={16} />
                      </button>
                      <span className="composer__recording" role="status">
                        <span className="composer__recording-dot" aria-hidden="true" />
                        {speech.elapsedSeconds}s
                      </span>
                      <button
                        type="button"
                        className="composer__mic composer__mic--cancel"
                        onClick={() => {
                          caretRef.current = null
                          speech.cancel()
                        }}
                        aria-label="Cancel recording"
                        title="Cancel recording"
                      >
                        <X size={16} />
                      </button>
                    </>
                  ) : (
                    <button
                      type="button"
                      className="composer__mic"
                      onClick={beginRecording}
                      disabled={disabled || transcribing}
                      aria-label="Start recording"
                      title="Start recording (dictate a message)"
                    >
                      {transcribing ? <Loader2 className="page__spinner" size={18} /> : <Mic size={18} />}
                    </button>
                  )}
                  {transcribing && <span className="composer__transcribing">Transcribing…</span>}
                </div>
              )}
            </div>
            <span className="composer__divider" aria-hidden="true" />
          </>
        )}
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
      {speech.error && (
        <p className="composer__speech-error" role="alert">
          {speech.error}
        </p>
      )}
      {speech.conversionNote && !speech.error && <p className="composer__speech-note">{speech.conversionNote}</p>}
    </div>
  )
}
