/**
 * Browser-native speech recognition (Web Speech API).
 *
 * Recognition runs in the browser. Chromium-based browsers stream the audio to a
 * browser-managed recognition service, so it needs a network connection and is
 * not guaranteed to work offline. FitAI never receives, stores or uploads the
 * audio: only the recognised text reaches the chat composer, and only when the
 * user sends it.
 */

/** Minimal typings: the Web Speech API is not part of every TypeScript DOM lib. */
export interface SpeechRecognitionAlternativeLike {
  transcript: string
  confidence: number
}

export interface SpeechRecognitionResultLike {
  readonly length: number
  readonly isFinal: boolean
  [index: number]: SpeechRecognitionAlternativeLike
}

export interface SpeechRecognitionResultListLike {
  readonly length: number
  [index: number]: SpeechRecognitionResultLike
}

export interface SpeechRecognitionEventLike {
  readonly resultIndex: number
  readonly results: SpeechRecognitionResultListLike
}

export interface SpeechRecognitionErrorEventLike {
  readonly error: string
  readonly message?: string
}

export interface SpeechRecognitionLike {
  lang: string
  continuous: boolean
  interimResults: boolean
  maxAlternatives: number
  onstart: (() => void) | null
  onend: (() => void) | null
  onerror: ((event: SpeechRecognitionErrorEventLike) => void) | null
  onresult: ((event: SpeechRecognitionEventLike) => void) | null
  start: () => void
  stop: () => void
  abort: () => void
}

export type SpeechRecognitionConstructor = new () => SpeechRecognitionLike

export interface SpeechLanguage {
  code: string
  label: string
}

/**
 * Languages offered in the picker. Browsers expose no reliable list of what the
 * recognition service supports, so a language that is not available surfaces as
 * a `language-not-supported` error at start instead of being pre-filtered.
 */
export const SPEECH_LANGUAGES: readonly SpeechLanguage[] = [
  { code: 'en-IN', label: 'English (India)' },
  { code: 'en-US', label: 'English (US)' },
  { code: 'ta-IN', label: 'Tamil' },
  { code: 'hi-IN', label: 'Hindi' },
]

export const DEFAULT_SPEECH_LANGUAGE = 'en-IN'
const LANGUAGE_STORAGE_KEY = 'fitai.speechLanguage'

export function isKnownSpeechLanguage(code: string | null | undefined): code is string {
  return SPEECH_LANGUAGES.some((language) => language.code === code)
}

/** The user's saved choice, else their browser language when offered, else en-IN. */
export function initialSpeechLanguage(): string {
  try {
    const saved = window.localStorage.getItem(LANGUAGE_STORAGE_KEY)
    if (isKnownSpeechLanguage(saved)) return saved
  } catch {
    // Storage can be blocked (private mode); fall through to the default.
  }
  const browser = typeof navigator !== 'undefined' ? navigator.language : ''
  return isKnownSpeechLanguage(browser) ? browser : DEFAULT_SPEECH_LANGUAGE
}

export function saveSpeechLanguage(code: string): void {
  try {
    window.localStorage.setItem(LANGUAGE_STORAGE_KEY, code)
  } catch {
    // Not persisting the preference is harmless.
  }
}

/** The recognition constructor, if this browser has one. */
export function getSpeechRecognitionConstructor(): SpeechRecognitionConstructor | null {
  if (typeof window === 'undefined') return null
  const scope = window as unknown as {
    SpeechRecognition?: SpeechRecognitionConstructor
    webkitSpeechRecognition?: SpeechRecognitionConstructor
  }
  return scope.SpeechRecognition ?? scope.webkitSpeechRecognition ?? null
}

export type SpeechSupport =
  | { supported: true }
  | { supported: false; reason: 'no-api' | 'insecure-context'; message: string }

/**
 * Whether dictation can work here. Microphone access needs a secure context
 * (HTTPS; `localhost` counts as secure for development).
 */
export function detectSpeechSupport(): SpeechSupport {
  if (typeof window !== 'undefined' && window.isSecureContext === false) {
    return {
      supported: false,
      reason: 'insecure-context',
      message: 'Voice input needs a secure (HTTPS) connection. Open FitAI over HTTPS to dictate.',
    }
  }
  if (!getSpeechRecognitionConstructor()) {
    return {
      supported: false,
      reason: 'no-api',
      message: 'Voice input is not supported in this browser. Use Chrome or Edge, or type your message.',
    }
  }
  return { supported: true }
}

/** Maps a Web Speech `error` code to guidance the user can act on. */
export function describeSpeechError(code: string): string {
  switch (code) {
    case 'not-allowed':
      return 'Microphone access was blocked, or the permission prompt was dismissed. Allow the microphone for this site in your browser’s address-bar or site settings, then try again.'
    case 'service-not-allowed':
      return 'The browser’s speech recognition service is not allowed here. Check that the browser permits speech recognition and that the page uses HTTPS.'
    case 'audio-capture':
      return 'No microphone was found, or it is in use by another app. Connect a microphone and try again.'
    case 'network':
      return 'Speech recognition could not reach the browser’s recognition service. Check your connection and try again, or type your message.'
    case 'no-speech':
      return 'No speech was detected. Check your microphone and try again.'
    case 'language-not-supported':
      return 'This browser does not support speech recognition in the selected language. Choose another language.'
    case 'bad-grammar':
      return 'Speech recognition is not configured correctly in this browser.'
    default:
      return 'Voice input stopped unexpectedly. Please try again.'
  }
}
