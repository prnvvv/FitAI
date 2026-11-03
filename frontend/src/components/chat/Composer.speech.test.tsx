/**
 * Dictation in the chat composer, with the browser SpeechRecognition mocked.
 * These tests prove the wiring; real microphone behaviour needs the manual
 * browser checklist in docs/SPEECH_TO_TEXT.md.
 */
import { act, fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { FakeSpeechRecognition } from '../../test/fakeSpeechRecognition'
import { Composer } from './Composer'

beforeEach(() => {
  vi.spyOn(navigator, 'language', 'get').mockReturnValue('fr-FR')
  window.localStorage.clear()
  FakeSpeechRecognition.install()
})

afterEach(() => {
  vi.restoreAllMocks()
  FakeSpeechRecognition.uninstall()
})

const textbox = () => screen.getByRole('textbox', { name: 'Message' }) as HTMLTextAreaElement

async function startListening(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('button', { name: 'Start voice input' }))
  act(() => FakeSpeechRecognition.last.emitStart())
}

describe('composer voice input', () => {
  it('offers the microphone and language picker when the browser supports it', () => {
    render(<Composer onSend={vi.fn()} />)
    expect(screen.getByRole('button', { name: 'Start voice input' })).toBeEnabled()
    expect(screen.getByRole('combobox', { name: 'Voice input language' })).toHaveValue('en-IN')
    expect(FakeSpeechRecognition.instances).toHaveLength(0)
  })

  it('inserts final speech into the textarea and never sends by itself', async () => {
    const user = userEvent.setup()
    const onSend = vi.fn()
    render(<Composer onSend={onSend} />)

    await startListening(user)
    expect(screen.getByRole('status')).toHaveTextContent('Listening')
    act(() => FakeSpeechRecognition.last.emitResults([{ text: 'how much protein', isFinal: false }]))
    expect(screen.getByRole('status')).toHaveTextContent('how much protein')
    expect(textbox()).toHaveValue('')

    act(() => FakeSpeechRecognition.last.emitResults([{ text: 'how much protein', isFinal: true }]))
    expect(textbox()).toHaveValue('how much protein')

    await user.click(screen.getByRole('button', { name: 'Stop voice input' }))
    expect(screen.getByRole('status')).toHaveTextContent('Review and edit')
    expect(onSend).not.toHaveBeenCalled()
  })

  it('keeps typed text and inserts at the caret', async () => {
    const user = userEvent.setup()
    render(<Composer onSend={vi.fn()} />)

    fireEvent.change(textbox(), { target: { value: 'Plan my  workout' } })
    textbox().setSelectionRange(8, 8)

    await startListening(user)
    act(() => FakeSpeechRecognition.last.emitResults([{ text: 'leg day', isFinal: true }]))
    expect(textbox()).toHaveValue('Plan my leg day workout')
  })

  it('appends several phrases in order without duplicating them', async () => {
    const user = userEvent.setup()
    render(<Composer onSend={vi.fn()} />)
    fireEvent.change(textbox(), { target: { value: 'Hi' } })
    textbox().setSelectionRange(2, 2)

    await startListening(user)
    const rec = FakeSpeechRecognition.last
    act(() => rec.emitResults([{ text: 'first', isFinal: true }]))
    act(() => rec.emitResults([{ text: 'first', isFinal: true }], 0))
    act(() =>
      rec.emitResults(
        [
          { text: 'first', isFinal: true },
          { text: 'second', isFinal: true },
        ],
        1,
      ),
    )
    expect(textbox()).toHaveValue('Hi first second')
  })

  it('lets the user edit the transcript and then sends the edited text', async () => {
    const user = userEvent.setup()
    const onSend = vi.fn()
    render(<Composer onSend={onSend} />)

    await startListening(user)
    act(() => FakeSpeechRecognition.last.emitResults([{ text: 'log my run', isFinal: true }]))
    await user.click(screen.getByRole('button', { name: 'Stop voice input' }))

    fireEvent.change(textbox(), { target: { value: 'log my 5k run' } })
    await user.click(screen.getByRole('button', { name: 'Send message' }))
    expect(onSend).toHaveBeenCalledTimes(1)
    expect(onSend).toHaveBeenCalledWith('log my 5k run')
    expect(textbox()).toHaveValue('')
  })

  it('blocks sending while dictating so words are not lost', async () => {
    const user = userEvent.setup()
    const onSend = vi.fn()
    render(<Composer onSend={onSend} />)
    fireEvent.change(textbox(), { target: { value: 'draft' } })

    await startListening(user)
    expect(screen.getByRole('button', { name: 'Send message' })).toBeDisabled()
    fireEvent.keyDown(textbox(), { key: 'Enter' })
    expect(onSend).not.toHaveBeenCalled()
  })

  it('passes the chosen language to the recognizer', async () => {
    const user = userEvent.setup()
    render(<Composer onSend={vi.fn()} />)
    await user.selectOptions(screen.getByRole('combobox', { name: 'Voice input language' }), 'ta-IN')
    await user.click(screen.getByRole('button', { name: 'Start voice input' }))
    expect(FakeSpeechRecognition.last.lang).toBe('ta-IN')
  })

  it('cancel discards the session and leaves the draft untouched', async () => {
    const user = userEvent.setup()
    render(<Composer onSend={vi.fn()} />)
    fireEvent.change(textbox(), { target: { value: 'keep me' } })

    await startListening(user)
    act(() => FakeSpeechRecognition.last.emitResults([{ text: 'ignored', isFinal: false }]))
    await user.click(screen.getByRole('button', { name: 'Cancel voice input' }))

    expect(textbox()).toHaveValue('keep me')
    expect(screen.getByRole('button', { name: 'Start voice input' })).toBeInTheDocument()
  })

  it('shows permission-denied guidance and reports it to the owner', async () => {
    const user = userEvent.setup()
    const onSpeechError = vi.fn()
    render(<Composer onSend={vi.fn()} onSpeechError={onSpeechError} />)

    await user.click(screen.getByRole('button', { name: 'Start voice input' }))
    act(() => FakeSpeechRecognition.last.emitError('not-allowed'))
    act(() => FakeSpeechRecognition.last.emitEnd())

    expect(await screen.findByRole('alert')).toHaveTextContent(/blocked/i)
    expect(onSpeechError).toHaveBeenCalledWith(expect.stringMatching(/blocked/i))
    expect(screen.getByRole('button', { name: 'Start voice input' })).toBeEnabled()
  })

  it('shows a network error from the recognition service', async () => {
    const user = userEvent.setup()
    render(<Composer onSend={vi.fn()} />)
    await startListening(user)
    act(() => FakeSpeechRecognition.last.emitError('network'))
    act(() => FakeSpeechRecognition.last.emitEnd())
    expect(await screen.findByRole('alert')).toHaveTextContent(/recognition service/i)
  })

  it('releases the microphone when the composer unmounts', async () => {
    const user = userEvent.setup()
    const { unmount } = render(<Composer onSend={vi.fn()} />)
    await startListening(user)
    const rec = FakeSpeechRecognition.last
    unmount()
    expect(rec.abort).toHaveBeenCalled()
  })
})

describe('composer voice input in an unsupported browser', () => {
  it('disables the microphone and explains what to do', async () => {
    FakeSpeechRecognition.uninstall()
    const user = userEvent.setup()
    render(<Composer onSend={vi.fn()} />)

    const mic = screen.getByRole('button', { name: 'Voice input unavailable' })
    expect(mic).toHaveAttribute('aria-disabled', 'true')
    expect(screen.queryByRole('combobox', { name: 'Voice input language' })).not.toBeInTheDocument()

    await user.click(mic)
    expect(screen.getByRole('alert')).toHaveTextContent(/Chrome or Edge/)
    expect(FakeSpeechRecognition.instances).toHaveLength(0)
  })

  it('still lets the user type and send', async () => {
    FakeSpeechRecognition.uninstall()
    const user = userEvent.setup()
    const onSend = vi.fn()
    render(<Composer onSend={onSend} />)
    await user.type(textbox(), 'typed{Enter}')
    expect(onSend).toHaveBeenCalledWith('typed')
  })
})
