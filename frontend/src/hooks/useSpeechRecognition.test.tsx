import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { FakeSpeechRecognition } from '../test/fakeSpeechRecognition'
import { useSpeechRecognition } from './useSpeechRecognition'

function setup() {
  const onFinalText = vi.fn()
  const onError = vi.fn()
  const hook = renderHook(() => useSpeechRecognition({ onFinalText, onError }))
  return { onFinalText, onError, ...hook }
}

beforeEach(() => {
  vi.useFakeTimers()
  window.localStorage.clear()
  FakeSpeechRecognition.install()
})

afterEach(() => {
  vi.restoreAllMocks()
  vi.useRealTimers()
  FakeSpeechRecognition.uninstall()
})

describe('useSpeechRecognition', () => {
  it('does not create a recognizer until start() is called', () => {
    const { result } = setup()
    expect(FakeSpeechRecognition.instances).toHaveLength(0)
    expect(result.current.status).toBe('idle')
    expect(result.current.isSupported).toBe(true)
  })

  it('configures and starts recognition with the selected language', () => {
    const { result } = setup()
    act(() => result.current.setLanguage('hi-IN'))
    act(() => result.current.start())

    const rec = FakeSpeechRecognition.last
    expect(rec.start).toHaveBeenCalledTimes(1)
    expect(rec).toMatchObject({ lang: 'hi-IN', continuous: true, interimResults: true })
    expect(result.current.status).toBe('requesting')
    act(() => rec.emitStart())
    expect(result.current.status).toBe('listening')
  })

  it('shows interim text without delivering it, then delivers final text once', () => {
    const { result, onFinalText } = setup()
    act(() => result.current.start())
    const rec = FakeSpeechRecognition.last
    act(() => rec.emitStart())

    act(() => rec.emitResults([{ text: 'how many', isFinal: false }]))
    expect(result.current.interim).toBe('how many')
    expect(onFinalText).not.toHaveBeenCalled()

    act(() => rec.emitResults([{ text: 'how many calories', isFinal: true }]))
    expect(onFinalText).toHaveBeenCalledTimes(1)
    expect(onFinalText).toHaveBeenCalledWith('how many calories')
    expect(result.current.interim).toBe('')
  })

  it('does not deliver a re-sent final result twice', () => {
    const { result, onFinalText } = setup()
    act(() => result.current.start())
    const rec = FakeSpeechRecognition.last
    act(() => rec.emitStart())

    act(() => rec.emitResults([{ text: 'leg day', isFinal: true }]))
    act(() => rec.emitResults([{ text: 'leg day', isFinal: true }], 0))
    act(() =>
      rec.emitResults(
        [
          { text: 'leg day', isFinal: true },
          { text: 'tomorrow', isFinal: true },
        ],
        0,
      ),
    )
    expect(onFinalText.mock.calls.map((c) => c[0])).toEqual(['leg day', 'tomorrow'])
  })

  it('ignores repeated start() calls while a session is active', () => {
    const { result } = setup()
    act(() => result.current.start())
    act(() => result.current.start())
    act(() => result.current.start())
    expect(FakeSpeechRecognition.instances).toHaveLength(1)
  })

  it('stop() finalizes, keeps unfinished words and completes', () => {
    const { result, onFinalText } = setup()
    act(() => result.current.start())
    const rec = FakeSpeechRecognition.last
    act(() => rec.emitStart())
    act(() => rec.emitResults([{ text: 'almost done', isFinal: false }]))

    act(() => result.current.stop())
    expect(rec.stop).toHaveBeenCalledTimes(1)
    expect(onFinalText).toHaveBeenCalledWith('almost done')
    expect(result.current.status).toBe('completed')

    act(() => {
      vi.advanceTimersByTime(2100)
    })
    expect(result.current.status).toBe('idle')
  })

  it('releases the recognizer if the browser never fires end after stop()', () => {
    const { result } = setup()
    act(() => result.current.start())
    const rec = FakeSpeechRecognition.last
    rec.stop.mockImplementation(() => {})
    act(() => rec.emitStart())
    act(() => rec.emitResults([{ text: 'hello', isFinal: true }]))
    act(() => result.current.stop())
    expect(result.current.status).toBe('finalizing')

    act(() => {
      vi.advanceTimersByTime(2600)
    })
    expect(rec.abort).toHaveBeenCalled()
    expect(result.current.status).toBe('completed')
  })

  it('cancel() aborts and discards everything', () => {
    const { result, onFinalText, onError } = setup()
    act(() => result.current.start())
    const rec = FakeSpeechRecognition.last
    act(() => rec.emitStart())
    act(() => rec.emitResults([{ text: 'discard me', isFinal: false }]))

    act(() => result.current.cancel())
    expect(rec.abort).toHaveBeenCalled()
    expect(result.current.status).toBe('idle')
    expect(result.current.interim).toBe('')
    // Late events from the cancelled session are ignored.
    act(() => rec.emitResults([{ text: 'late', isFinal: true }]))
    expect(onFinalText).not.toHaveBeenCalled()
    expect(onError).not.toHaveBeenCalled()
  })

  it('allows a new session after the previous one ended', () => {
    const { result } = setup()
    act(() => result.current.start())
    act(() => FakeSpeechRecognition.last.emitStart())
    act(() => FakeSpeechRecognition.last.emitResults([{ text: 'one', isFinal: true }]))
    act(() => result.current.stop())
    act(() => result.current.start())
    expect(FakeSpeechRecognition.instances).toHaveLength(2)
  })

  it.each([
    ['not-allowed', /blocked/i],
    ['service-not-allowed', /not allowed/i],
    ['audio-capture', /No microphone/i],
    ['network', /recognition service/i],
    ['language-not-supported', /language/i],
  ])('reports %s as an error with guidance', (code, pattern) => {
    const { result, onError, onFinalText } = setup()
    act(() => result.current.start())
    const rec = FakeSpeechRecognition.last
    act(() => rec.emitError(code))
    act(() => rec.emitEnd())

    expect(result.current.status).toBe('error')
    expect(result.current.error).toMatch(pattern)
    expect(onError).toHaveBeenCalledTimes(1)
    expect(onFinalText).not.toHaveBeenCalled()
  })

  it('reports no speech when the session ends with nothing heard', () => {
    const { result } = setup()
    act(() => result.current.start())
    act(() => FakeSpeechRecognition.last.emitStart())
    act(() => FakeSpeechRecognition.last.emitEnd())
    expect(result.current.status).toBe('error')
    expect(result.current.error).toMatch(/no speech/i)
  })

  it('treats an unexpected end after speech as completed, not an error', () => {
    const { result, onFinalText } = setup()
    act(() => result.current.start())
    act(() => FakeSpeechRecognition.last.emitStart())
    act(() => FakeSpeechRecognition.last.emitResults([{ text: 'warm up', isFinal: true }]))
    act(() => FakeSpeechRecognition.last.emitEnd())
    expect(onFinalText).toHaveBeenCalledWith('warm up')
    expect(result.current.status).toBe('completed')
  })

  it('reports a failure when start() throws and leaves no stuck session', () => {
    FakeSpeechRecognition.startError = new Error('already started')
    const { result } = setup()
    act(() => result.current.start())
    expect(result.current.status).toBe('error')
    FakeSpeechRecognition.startError = null
    act(() => result.current.start())
    expect(FakeSpeechRecognition.instances).toHaveLength(2)
  })

  it('stops when the tab becomes hidden', () => {
    const { result } = setup()
    act(() => result.current.start())
    act(() => FakeSpeechRecognition.last.emitStart())
    const visibility = vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden')
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'))
    })
    expect(FakeSpeechRecognition.last.stop).toHaveBeenCalled()
    visibility.mockRestore()
  })

  it('cancels on Escape', () => {
    const { result } = setup()
    act(() => result.current.start())
    act(() => FakeSpeechRecognition.last.emitStart())
    act(() => {
      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    })
    expect(FakeSpeechRecognition.last.abort).toHaveBeenCalled()
    expect(result.current.status).toBe('idle')
  })

  it('aborts the recognizer when unmounted mid-session', () => {
    const { result, unmount, onFinalText } = setup()
    act(() => result.current.start())
    act(() => FakeSpeechRecognition.last.emitStart())
    const rec = FakeSpeechRecognition.last
    unmount()
    expect(rec.abort).toHaveBeenCalled()
    act(() => rec.emitResults([{ text: 'too late', isFinal: true }]))
    expect(onFinalText).not.toHaveBeenCalled()
  })

  it('reports unsupported browsers and never creates a recognizer', () => {
    FakeSpeechRecognition.uninstall()
    const { result } = setup()
    expect(result.current.isSupported).toBe(false)
    expect(result.current.status).toBe('unsupported')
    expect(result.current.unsupportedMessage).toMatch(/Chrome or Edge/)
    act(() => result.current.start())
    expect(FakeSpeechRecognition.instances).toHaveLength(0)
  })
})
