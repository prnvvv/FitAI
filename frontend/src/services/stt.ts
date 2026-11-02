/**
 * Client for the Granite speech-to-text endpoint.
 *
 * The model lives inside the FitAI backend, so the default base URL is the
 * API base followed by `/stt` (`/api/v1/stt` in development). Override it with
 * `VITE_STT_URL` only if you are running a separate transcription service.
 *
 * Nothing about the model, its credentials or its environment is exposed to the
 * browser: this module only uploads audio and reads text back.
 */
import { getToken } from './supabase'

/**
 * Base URL for the STT routes. Defaults to `<API base>/stt`, so a deployment
 * that sets `VITE_API_BASE_URL` to the backend origin reaches the backend
 * rather than the static host. Override with VITE_STT_URL only for a separate
 * transcription service.
 */
const API_BASE: string = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'
export const STT_BASE_URL: string = (
  import.meta.env.VITE_STT_URL ?? `${API_BASE.replace(/\/+$/, '')}/stt`
).replace(/\/+$/, '')

/** A transcription that ran, including the case where nothing was recognised. */
export interface TranscriptionResult {
  text: string
  warning: string | null
  durationSeconds: number | null
}

export class TranscriptionError extends Error {
  /** True when the clip was unusable, so the caller should not retry it as-is. */
  readonly retryable: boolean

  constructor(message: string, retryable = true) {
    super(message)
    this.name = 'TranscriptionError'
    this.retryable = retryable
  }
}

export interface TranscribeOptions {
  signal?: AbortSignal
  timeoutMs?: number
}

const DEFAULT_TIMEOUT_MS = 60_000

function serviceHint(): string {
  if (STT_BASE_URL.startsWith('http')) {
    return `Is the transcription service running at ${STT_BASE_URL}?`
  }
  return 'Is the FitAI backend running? The microphone uses the same backend as chat.'
}

/**
 * Uploads a recorded clip and returns the recognised text.
 *
 * A 200 with no speech returns an empty string plus a warning; the caller keeps
 * the user's draft rather than replacing it with nothing.
 */
export async function transcribeAudio(
  blob: Blob,
  filename = 'recording.webm',
  options: TranscribeOptions = {},
): Promise<TranscriptionResult> {
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(new DOMException('Timed out', 'TimeoutError')), timeoutMs)
  const abort = () => controller.abort(options.signal?.reason)
  options.signal?.addEventListener('abort', abort)

  try {
    const body = new FormData()
    body.append('file', blob, filename)

    const headers = new Headers()
    const token = await getToken()
    if (token) {
      headers.set('Authorization', `Bearer ${token}`)
    }

    const response = await fetch(`${STT_BASE_URL}/transcribe`, {
      method: 'POST',
      body,
      headers,
      signal: controller.signal,
    })

    const payload = (await response.json().catch(() => null)) as
      | { text?: string; warning?: string; detail?: string; audio?: { duration_s?: number } }
      | null

    if (!response.ok) {
      const detail = payload?.detail ?? `Transcription failed (HTTP ${response.status})`
      // 422 means the audio itself is unusable; anything else may succeed later.
      throw new TranscriptionError(detail, response.status !== 422)
    }

    return {
      text: (payload?.text ?? '').trim(),
      warning: payload?.warning ?? null,
      durationSeconds: typeof payload?.audio?.duration_s === 'number' ? payload.audio.duration_s : null,
    }
  } catch (error) {
    if (error instanceof TranscriptionError) throw error
    if (options.signal?.aborted) throw error
    if (error instanceof DOMException && error.name === 'TimeoutError') {
      throw new TranscriptionError('The transcription service did not respond in time.', true)
    }
    throw new TranscriptionError(
      `Could not reach the speech-to-text service. ${serviceHint()}`,
      true,
    )
  } finally {
    clearTimeout(timeout)
    options.signal?.removeEventListener('abort', abort)
  }
}

/** Status of the service, used to explain an idle microphone control. */
export async function fetchTranscriptionStatus(
  signal?: AbortSignal,
): Promise<{ state: string; modelId: string; device: string }> {
  const headers = new Headers()
  const token = await getToken()
  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
  }

  const response = await fetch(`${STT_BASE_URL}/status`, { signal, headers })
  if (!response.ok) throw new TranscriptionError(`Service status unavailable (HTTP ${response.status})`, true)
  const payload = (await response.json()) as { state?: string; model_id?: string; device?: string }
  return {
    state: payload.state ?? 'unknown',
    modelId: payload.model_id ?? 'unknown',
    device: payload.device ?? 'unknown',
  }
}