/**
 * Microphone recording state for the chat composer.
 *
 * Responsibilities, kept out of the component so they can be tested without a
 * real microphone:
 *  - ask for permission only when the user clicks, then record;
 *  - guard against double clicks, repeated stops and stale requests;
 *  - drop a transcript that arrives after the user changed conversation;
 *  - cancel cleanly, without uploading or inserting anything.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { TranscriptionError, transcribeAudio } from '../services/stt'
import { preferredAudioMimeType, prepareAudioForUpload } from '../services/sttAudio'

export type SpeechStatus = 'idle' | 'recording' | 'transcribing'

/** Clips shorter than this carry no word, so they are never uploaded. */
const MIN_RECORDING_MS = 400

export interface SpeechToTextOptions {
  /** Called with the recognised text; the owner inserts it into its input. */
  onTranscript: (text: string) => void
  onError?: (message: string) => void
}

export interface SpeechToText {
  status: SpeechStatus
  /** Whole seconds since recording started, for the timer. */
  elapsedSeconds: number
  error: string | null
  conversionNote: string | null
  isSupported: boolean
  start: () => Promise<void>
  stop: () => void
  cancel: () => void
  dismissError: () => void
}

/** `getUserMedia` rejections are not always DOMException instances. */
function errorName(error: unknown): string {
  if (error instanceof DOMException) return error.name
  const name = (error as { name?: string } | null)?.name
  return typeof name === 'string' ? name : ''
}

function friendlyError(error: unknown): string {
  const name = errorName(error)
  if (name === 'NotAllowedError' || name === 'SecurityError') {
    return 'Microphone access was blocked. Allow it in your browser settings and try again.'
  }
  if (name === 'NotFoundError' || name === 'DevicesNotFoundError') {
    return 'No microphone was found on this device.'
  }
  if (name === 'NotReadableError' || name === 'TrackStartError') {
    return 'The microphone is busy in another app.'
  }
  if (error instanceof TranscriptionError) return error.message
  if (error instanceof Error) return error.message
  return 'Recording failed. Please try again.'
}

/**
 * The owner must key the component by conversation: unmounting cancels the
 * recording and invalidates any transcript still in flight, so text can never
 * land in another conversation.
 */
export function useSpeechToText({ onTranscript, onError }: SpeechToTextOptions): SpeechToText {
  const [status, setStatus] = useState<SpeechStatus>('idle')
  const [elapsedSeconds, setElapsedSeconds] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [conversionNote, setConversionNote] = useState<string | null>(null)

  const recorderRef = useRef<MediaRecorder | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const chunksRef = useRef<BlobPart[]>([])
  const startedAtRef = useRef(0)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  /** Increments per action so late results from an older action are ignored. */
  const tokenRef = useRef(0)
  const busyRef = useRef(false)
  const cancelRef = useRef<() => void>(() => {})
  const onTranscriptRef = useRef(onTranscript)
  const onErrorRef = useRef(onError)

  useEffect(() => {
    onTranscriptRef.current = onTranscript
    onErrorRef.current = onError
  }, [onTranscript, onError])

  const clearTimer = useCallback(() => {
    if (timerRef.current !== null) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }
  }, [])

  const releaseStream = useCallback(() => {
    clearTimer()
    streamRef.current?.getTracks().forEach((track) => track.stop())
    streamRef.current = null
    recorderRef.current = null
    setElapsedSeconds(0)
  }, [clearTimer])

  // Leaving the conversation (or unmounting) must not leave the mic open.
  useEffect(
    () => () => {
      tokenRef.current += 1
      releaseStream()
    },
    [releaseStream],
  )

  // Escape cancels a recording wherever focus happens to be, including the page
  // body: a recording must never be stuck open because focus moved.
  useEffect(() => {
    if (status !== 'recording') return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return
      event.preventDefault()
      cancelRef.current()
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [status])

  const report = useCallback(
    (message: string) => {
      setError(message)
      onErrorRef.current?.(message)
    },
    [],
  )

  const finish = useCallback(
    async (blob: Blob, token: number, elapsedMs: number) => {
      if (token !== tokenRef.current) return

      if (blob.size === 0 || elapsedMs < MIN_RECORDING_MS) {
        setStatus('idle')
        report('That recording was too short. Hold the mic and speak for at least a second.')
        return
      }

      setStatus('transcribing')
      try {
        const prepared = await prepareAudioForUpload(blob)
        if (token !== tokenRef.current) return
        setConversionNote(prepared.conversionNote)

        const result = await transcribeAudio(prepared.blob, prepared.filename)
        if (token !== tokenRef.current) return
        busyRef.current = false

        if (!result.text) {
          setStatus('idle')
          report(result.warning ?? 'No speech was recognised. Try again, or type your message.')
          return
        }
        setStatus('idle')
        onTranscriptRef.current(result.text)
      } catch (caught) {
        if (token !== tokenRef.current) return
        busyRef.current = false
        setStatus('idle')
        if (errorName(caught) === 'AbortError') return
        report(friendlyError(caught))
      }
    },
    [report],
  )

  const start = useCallback(async () => {
    if (busyRef.current || recorderRef.current) return
    if (typeof navigator === 'undefined' || !navigator.mediaDevices?.getUserMedia) {
      report('This browser cannot record audio.')
      return
    }

    setError(null)
    setConversionNote(null)
    busyRef.current = true
    const token = (tokenRef.current += 1)

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
      })
      if (token !== tokenRef.current) {
        stream.getTracks().forEach((track) => track.stop())
        return
      }
      streamRef.current = stream

      const mimeType = preferredAudioMimeType()
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined)
      chunksRef.current = []
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data)
      }
      recorder.onstop = () => {
        const elapsedMs = Date.now() - startedAtRef.current
        const blob = new Blob(chunksRef.current, { type: recorder.mimeType || mimeType || 'audio/webm' })
        chunksRef.current = []
        releaseStream()
        void finish(blob, token, elapsedMs)
      }
      recorderRef.current = recorder
      recorder.start()
      startedAtRef.current = Date.now()
      setStatus('recording')
      timerRef.current = setInterval(() => {
        setElapsedSeconds(Math.floor((Date.now() - startedAtRef.current) / 1000))
      }, 250)
    } catch (caught) {
      busyRef.current = false
      releaseStream()
      if (token === tokenRef.current) report(friendlyError(caught))
    }
  }, [finish, releaseStream, report])

  const stop = useCallback(() => {
    const recorder = recorderRef.current
    if (!recorder || recorder.state === 'inactive') return
    recorder.stop()
  }, [])

  const cancel = useCallback(() => {
    // Bumping the token makes the pending onstop handler a no-op, so nothing is
    // uploaded and nothing is inserted.
    tokenRef.current += 1
    busyRef.current = false
    chunksRef.current = []
    const recorder = recorderRef.current
    if (recorder && recorder.state !== 'inactive') recorder.stop()
    releaseStream()
    setStatus('idle')
    setError(null)
  }, [releaseStream])

  const dismissError = useCallback(() => setError(null), [])

  // Kept in a ref so the Escape listener always calls the current cancel.
  useEffect(() => {
    cancelRef.current = cancel
  }, [cancel])

  const isSupported =
    typeof navigator !== 'undefined' && !!navigator.mediaDevices?.getUserMedia && typeof MediaRecorder !== 'undefined'

  return {
    status,
    elapsedSeconds,
    error,
    conversionNote,
    isSupported,
    start,
    stop,
    cancel,
    dismissError,
  }
}