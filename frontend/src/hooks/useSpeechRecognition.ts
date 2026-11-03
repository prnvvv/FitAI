/**
 * Dictation state for the chat composer, built on the browser Web Speech API.
 *
 * Kept out of the component so it can be tested with a mocked recognition
 * object. Guarantees:
 *  - the microphone permission is requested only from an explicit `start()`;
 *  - at most one recognition instance exists at a time;
 *  - every finalised result is delivered once (tracked by result index);
 *  - unmounting, `cancel()`, Escape and hiding the tab all release the microphone;
 *  - nothing is ever sent: the owner decides what to do with the text.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import {
  describeSpeechError,
  detectSpeechSupport,
  getSpeechRecognitionConstructor,
  initialSpeechLanguage,
  saveSpeechLanguage,
  type SpeechRecognitionLike,
} from '../services/speechRecognition'

export type SpeechStatus =
  | 'idle'
  | 'requesting'
  | 'listening'
  | 'finalizing'
  | 'completed'
  | 'error'
  | 'unsupported'

/** Safety net: a session never keeps the microphone open longer than this. */
const MAX_SESSION_MS = 60_000
/** If the browser never fires `end` after `stop()`, release it after this long. */
const STOP_GRACE_MS = 2_500
/** How long the "completed" confirmation stays visible. */
const COMPLETED_VISIBLE_MS = 2_000

export interface SpeechRecognitionOptions {
  /** Receives each finalised phrase exactly once. */
  onFinalText: (text: string) => void
  onError?: (message: string) => void
}

export interface SpeechRecognitionState {
  status: SpeechStatus
  /** Words heard but not yet finalised; shown live, never inserted. */
  interim: string
  error: string | null
  isSupported: boolean
  /** Why dictation is unavailable, when it is. */
  unsupportedMessage: string | null
  language: string
  setLanguage: (code: string) => void
  start: () => void
  stop: () => void
  cancel: () => void
  dismissError: () => void
}

interface Session {
  recognition: SpeechRecognitionLike
  emitted: Set<number>
  interim: string
  deliveredText: boolean
  stopRequested: boolean
  errorCode: string | null
  done: boolean
}

export function useSpeechRecognition({
  onFinalText,
  onError,
}: SpeechRecognitionOptions): SpeechRecognitionState {
  const [support] = useState(detectSpeechSupport)
  const [state, setState] = useState<SpeechStatus>('idle')
  const [interim, setInterim] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [language, setLanguageState] = useState(initialSpeechLanguage)

  const sessionRef = useRef<Session | null>(null)
  const maxTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const stopTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const completedTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const onFinalTextRef = useRef(onFinalText)
  const onErrorRef = useRef(onError)

  useEffect(() => {
    onFinalTextRef.current = onFinalText
    onErrorRef.current = onError
  }, [onFinalText, onError])

  const clearTimers = useCallback(() => {
    for (const ref of [maxTimerRef, stopTimerRef, completedTimerRef]) {
      if (ref.current !== null) {
        clearTimeout(ref.current)
        ref.current = null
      }
    }
  }, [])

  const report = useCallback((message: string) => {
    setError(message)
    setState('error')
    onErrorRef.current?.(message)
  }, [])

  /** Ends a session exactly once, whichever path (end, grace timeout) gets here first. */
  const finalize = useCallback(
    (session: Session) => {
      if (session.done) return
      session.done = true
      clearTimers()
      if (sessionRef.current === session) sessionRef.current = null
      setInterim('')

      if (session.errorCode) {
        report(describeSpeechError(session.errorCode))
        return
      }
      // Whatever was heard but not yet marked final is kept rather than lost.
      const pending = session.interim.trim()
      if (pending) {
        session.deliveredText = true
        onFinalTextRef.current(pending)
      }
      if (session.deliveredText) {
        setState('completed')
        completedTimerRef.current = setTimeout(() => setState('idle'), COMPLETED_VISIBLE_MS)
        return
      }
      report(describeSpeechError('no-speech'))
    },
    [clearTimers, report],
  )

  const stop = useCallback(() => {
    const session = sessionRef.current
    if (!session || session.done || session.stopRequested) return
    session.stopRequested = true
    setState('finalizing')
    try {
      session.recognition.stop()
    } catch {
      finalize(session)
      return
    }
    stopTimerRef.current = setTimeout(() => {
      try {
        session.recognition.abort()
      } catch {
        // Already gone; finalize below releases our side.
      }
      finalize(session)
    }, STOP_GRACE_MS)
  }, [finalize])

  const cancel = useCallback(() => {
    const session = sessionRef.current
    clearTimers()
    if (session && !session.done) {
      // Marking it done first makes every late event a no-op: nothing is inserted.
      session.done = true
      sessionRef.current = null
      try {
        session.recognition.abort()
      } catch {
        // Nothing to abort.
      }
    }
    setInterim('')
    setError(null)
    setState('idle')
  }, [clearTimers])

  const start = useCallback(() => {
    if (!support.supported) return
    // One instance at a time: repeated clicks while active are ignored.
    if (sessionRef.current) return
    const Recognition = getSpeechRecognitionConstructor()
    if (!Recognition) return

    clearTimers()
    setError(null)
    setInterim('')

    const recognition = new Recognition()
    recognition.lang = language
    recognition.continuous = true
    recognition.interimResults = true
    recognition.maxAlternatives = 1

    const session: Session = {
      recognition,
      emitted: new Set(),
      interim: '',
      deliveredText: false,
      stopRequested: false,
      errorCode: null,
      done: false,
    }
    const live = () => !session.done && sessionRef.current === session

    recognition.onstart = () => {
      if (!live()) return
      setState((current) => (current === 'requesting' ? 'listening' : current))
      maxTimerRef.current = setTimeout(stop, MAX_SESSION_MS)
    }

    recognition.onresult = (event) => {
      if (!live()) return
      let pending = ''
      for (let index = event.resultIndex; index < event.results.length; index += 1) {
        const result = event.results[index]
        const text = (result[0]?.transcript ?? '').trim()
        if (result.isFinal) {
          // Some browsers re-send earlier results; deliver each index once.
          if (session.emitted.has(index)) continue
          session.emitted.add(index)
          if (text) {
            session.deliveredText = true
            onFinalTextRef.current(text)
          }
        } else if (text) {
          pending = `${pending} ${text}`.trim()
        }
      }
      session.interim = pending
      setInterim(pending)
    }

    recognition.onerror = (event) => {
      if (session.done) return
      // `aborted` is our own cancel/abort, not a failure.
      if (event.error === 'aborted') return
      session.errorCode = event.error
    }

    recognition.onend = () => finalize(session)

    sessionRef.current = session
    setState('requesting')
    try {
      recognition.start()
    } catch {
      session.done = true
      sessionRef.current = null
      report(describeSpeechError('audio-capture'))
    }
  }, [clearTimers, finalize, language, report, stop, support])

  const setLanguage = useCallback((code: string) => {
    setLanguageState(code)
    saveSpeechLanguage(code)
  }, [])

  const dismissError = useCallback(() => {
    setError(null)
    setState((current) => (current === 'error' ? 'idle' : current))
  }, [])

  const active = state === 'requesting' || state === 'listening' || state === 'finalizing'

  // Hiding the tab stops listening: the microphone must not stay open unseen.
  useEffect(() => {
    if (!active) return
    const onVisibility = () => {
      if (document.visibilityState === 'hidden') stop()
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return
      event.preventDefault()
      cancel()
    }
    document.addEventListener('visibilitychange', onVisibility)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('visibilitychange', onVisibility)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [active, cancel, stop])

  // Unmounting (e.g. switching conversation) releases the microphone and drops
  // anything still in flight.
  useEffect(() => cancel, [cancel])

  return {
    status: support.supported ? state : 'unsupported',
    interim,
    error,
    isSupported: support.supported,
    unsupportedMessage: support.supported ? null : support.message,
    language,
    setLanguage,
    start,
    stop,
    cancel,
    dismissError,
  }
}
