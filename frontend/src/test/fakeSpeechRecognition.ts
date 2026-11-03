/** Controllable stand-in for the browser SpeechRecognition API, for tests only. */
import { vi } from 'vitest'
import type {
  SpeechRecognitionErrorEventLike,
  SpeechRecognitionEventLike,
  SpeechRecognitionLike,
} from '../services/speechRecognition'

export class FakeSpeechRecognition implements SpeechRecognitionLike {
  static instances: FakeSpeechRecognition[] = []
  static startError: Error | null = null

  lang = ''
  continuous = false
  interimResults = false
  maxAlternatives = 1
  onstart: (() => void) | null = null
  onend: (() => void) | null = null
  onerror: ((event: SpeechRecognitionErrorEventLike) => void) | null = null
  onresult: ((event: SpeechRecognitionEventLike) => void) | null = null

  start = vi.fn(() => {
    if (FakeSpeechRecognition.startError) throw FakeSpeechRecognition.startError
  })
  // Like a real browser, stop() ends the session after delivering results.
  stop = vi.fn(() => this.onend?.())
  abort = vi.fn(() => {
    this.onerror?.({ error: 'aborted' })
    this.onend?.()
  })

  constructor() {
    FakeSpeechRecognition.instances.push(this)
  }

  /** Permission granted and audio capture began. */
  emitStart() {
    this.onstart?.()
  }

  /**
   * Emits a results event. `results` is the full list so far, as browsers send
   * it; `resultIndex` is the first entry that changed.
   */
  emitResults(results: Array<{ text: string; isFinal: boolean }>, resultIndex = 0) {
    const list = results.map((entry) => ({
      0: { transcript: entry.text, confidence: 0.9 },
      length: 1,
      isFinal: entry.isFinal,
    }))
    this.onresult?.({ resultIndex, results: list as unknown as SpeechRecognitionEventLike['results'] })
  }

  emitError(error: string) {
    this.onerror?.({ error })
  }

  emitEnd() {
    this.onend?.()
  }

  static get last(): FakeSpeechRecognition {
    return FakeSpeechRecognition.instances[FakeSpeechRecognition.instances.length - 1]
  }

  static install(kind: 'standard' | 'webkit' = 'standard') {
    FakeSpeechRecognition.uninstall()
    const scope = window as unknown as Record<string, unknown>
    scope[kind === 'standard' ? 'SpeechRecognition' : 'webkitSpeechRecognition'] = FakeSpeechRecognition
  }

  static uninstall() {
    const scope = window as unknown as Record<string, unknown>
    delete scope.SpeechRecognition
    delete scope.webkitSpeechRecognition
    FakeSpeechRecognition.instances = []
    FakeSpeechRecognition.startError = null
  }
}
