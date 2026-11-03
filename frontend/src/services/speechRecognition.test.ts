import { afterEach, describe, expect, it, vi } from 'vitest'
import { FakeSpeechRecognition } from '../test/fakeSpeechRecognition'
import {
  DEFAULT_SPEECH_LANGUAGE,
  SPEECH_LANGUAGES,
  describeSpeechError,
  detectSpeechSupport,
  getSpeechRecognitionConstructor,
  initialSpeechLanguage,
  saveSpeechLanguage,
} from './speechRecognition'

afterEach(() => {
  vi.restoreAllMocks()
  FakeSpeechRecognition.uninstall()
  window.localStorage.clear()
})

describe('speech support detection', () => {
  it('reports unsupported when neither constructor exists', () => {
    FakeSpeechRecognition.uninstall()
    expect(getSpeechRecognitionConstructor()).toBeNull()
    expect(detectSpeechSupport()).toMatchObject({ supported: false, reason: 'no-api' })
  })

  it('uses the standard constructor when present', () => {
    FakeSpeechRecognition.install('standard')
    expect(getSpeechRecognitionConstructor()).toBe(FakeSpeechRecognition)
    expect(detectSpeechSupport()).toEqual({ supported: true })
  })

  it('falls back to the webkit-prefixed constructor', () => {
    FakeSpeechRecognition.install('webkit')
    expect(getSpeechRecognitionConstructor()).toBe(FakeSpeechRecognition)
    expect(detectSpeechSupport().supported).toBe(true)
  })

  it('refuses insecure contexts even when the API exists', () => {
    FakeSpeechRecognition.install()
    Object.defineProperty(window, 'isSecureContext', { configurable: true, value: false })
    try {
      expect(detectSpeechSupport()).toMatchObject({ supported: false, reason: 'insecure-context' })
    } finally {
      Object.defineProperty(window, 'isSecureContext', { configurable: true, value: true })
    }
  })
})

describe('speech language', () => {
  it('offers the four required languages', () => {
    expect(SPEECH_LANGUAGES.map((l) => l.code)).toEqual(['en-IN', 'en-US', 'ta-IN', 'hi-IN'])
  })

  it('defaults to en-IN, honours a saved choice and ignores unknown values', () => {
    vi.spyOn(navigator, 'language', 'get').mockReturnValue('fr-FR')
    expect(initialSpeechLanguage()).toBe(DEFAULT_SPEECH_LANGUAGE)
    saveSpeechLanguage('ta-IN')
    expect(initialSpeechLanguage()).toBe('ta-IN')
    window.localStorage.setItem('fitai.speechLanguage', 'xx-XX')
    expect(initialSpeechLanguage()).toBe(DEFAULT_SPEECH_LANGUAGE)
  })
})

describe('speech language from the browser', () => {
  it('uses the browser language when it is one of the offered languages', () => {
    vi.spyOn(navigator, 'language', 'get').mockReturnValue('hi-IN')
    expect(initialSpeechLanguage()).toBe('hi-IN')
  })
})

describe('speech error messages', () => {
  it.each([
    ['not-allowed', /blocked/i],
    ['audio-capture', /microphone/i],
    ['network', /connection/i],
    ['no-speech', /no speech/i],
    ['language-not-supported', /language/i],
    ['something-new', /unexpectedly/i],
  ])('explains %s', (code, pattern) => {
    expect(describeSpeechError(code)).toMatch(pattern)
  })
})
