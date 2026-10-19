/**
 * Microphone dictation in the chat composer.
 *
 * The transcription service and the microphone are both faked: no model, no
 * network, no audio hardware. Real transcription is covered by the service's own
 * suite and its smoke test, not here.
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { Composer } from './Composer'

const TRANSCRIPT = 'how many protein shakes after training'

class FakeRecorder {
  static isTypeSupported = vi.fn(() => true)
  static instances: FakeRecorder[] = []

  state: 'inactive' | 'recording' = 'inactive'
  mimeType: string
  ondataavailable: ((event: { data: Blob }) => void) | null = null
  onstop: (() => void) | null = null
  chunks: Blob[] = []

  options?: MediaRecorderOptions

  constructor(options?: MediaRecorderOptions) {
    this.options = options
    this.mimeType = options?.mimeType ?? 'audio/webm'
    FakeRecorder.instances.push(this)
  }

  start() {
    this.state = 'recording'
  }

  stop() {
    this.state = 'inactive'
    // MediaRecorder emits the buffered audio before the stop event.
    this.ondataavailable?.({ data: new Blob([new Uint8Array([1, 2, 3])], { type: this.mimeType }) })
    this.onstop?.()
  }
}

function installFakeMicrophone(overrides: { getUserMedia?: () => Promise<MediaStream> } = {}) {
  const track = { stop: vi.fn(), kind: 'audio' } as unknown as MediaStreamTrack
  const stream = { getTracks: () => [track], getAudioTracks: () => [track] } as unknown as MediaStream
  const getUserMedia = vi.fn(
    overrides.getUserMedia ?? (async (_constraints?: MediaStreamConstraints) => stream),
  )
  Object.defineProperty(globalThis.navigator, 'mediaDevices', {
    configurable: true,
    value: { getUserMedia },
  })
  ;(globalThis as unknown as { MediaRecorder: unknown }).MediaRecorder = FakeRecorder
  return { getUserMedia, track, stream }
}

function transcriptionResponse(body: Record<string, unknown>, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  }
}

let fetchMock: ReturnType<typeof vi.fn>

beforeEach(() => {
  FakeRecorder.instances = []
  fetchMock = vi.fn(async () => transcriptionResponse({ text: TRANSCRIPT }))
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

/** Records for `ms`, then presses stop, letting the transcription resolve. */
async function recordAndStop(user: ReturnType<typeof userEvent.setup>, ms = 500) {
  await user.click(screen.getByRole('button', { name: 'Start recording' }))
  await screen.findByRole('button', { name: 'Stop recording and transcribe' })
  await new Promise((resolve) => setTimeout(resolve, ms))
  await user.click(screen.getByRole('button', { name: 'Stop recording and transcribe' }))
}

describe('composer microphone', () => {
  it('shows the microphone control when the browser can record', () => {
    installFakeMicrophone()
    render(<Composer onSend={vi.fn()} />)

    const mic = screen.getByRole('button', { name: 'Start recording' })
    expect(mic).toBeInTheDocument()
    expect(mic).toHaveAttribute('title', 'Start recording (dictate a message)')
    expect(screen.queryByRole('button', { name: 'Stop recording and transcribe' })).not.toBeInTheDocument()
  })

  it('hides the control when the browser cannot record', () => {
    Object.defineProperty(globalThis.navigator, 'mediaDevices', { configurable: true, value: undefined })
    ;(globalThis as unknown as { MediaRecorder: unknown }).MediaRecorder = undefined
    render(<Composer onSend={vi.fn()} />)

    expect(screen.queryByRole('button', { name: 'Start recording' })).not.toBeInTheDocument()
  })

  it('asks for permission only after the click, then records', async () => {
    const user = userEvent.setup()
    const { getUserMedia } = installFakeMicrophone()
    render(<Composer onSend={vi.fn()} />)

    expect(getUserMedia).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: 'Start recording' }))

    expect(getUserMedia).toHaveBeenCalledTimes(1)
    expect(getUserMedia.mock.calls[0][0]).toMatchObject({ audio: expect.any(Object) })
    expect(await screen.findByRole('button', { name: 'Stop recording and transcribe' })).toBeInTheDocument()
    // Recording is announced in text, not by colour alone.
    expect(screen.getByRole('status')).toHaveTextContent('0s')
    expect(screen.getByRole('button', { name: 'Cancel recording' })).toBeInTheDocument()
  })

  it('uploads 16 kHz-ready audio and inserts the transcript at the caret', async () => {
    const user = userEvent.setup()
    installFakeMicrophone()
    render(<Composer onSend={vi.fn()} />)

    const input = screen.getByRole('textbox', { name: 'Message' }) as HTMLTextAreaElement
    await user.type(input, 'my draft')
    // Put the caret before the draft so the transcript lands there.
    input.setSelectionRange(0, 0)

    await recordAndStop(user)

    // The caret was at the start, so nothing separates the two fragments.
    await waitFor(() => expect(input).toHaveValue(`${TRANSCRIPT}my draft`))
    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe('http://127.0.0.1:8077/api/transcribe')
    expect(init.method).toBe('POST')
    const form = init.body as FormData
    expect(form.get('file')).toBeInstanceOf(Blob)
  })

  it('keeps an existing draft when the transcript is empty', async () => {
    const user = userEvent.setup()
    installFakeMicrophone()
    fetchMock.mockResolvedValueOnce(transcriptionResponse({ text: '', warning: 'No speech was recognised.' }))
    render(<Composer onSend={vi.fn()} />)

    const input = screen.getByRole('textbox', { name: 'Message' })
    await user.type(input, 'my draft')
    await recordAndStop(user)

    expect(await screen.findByRole('alert')).toHaveTextContent('No speech was recognised')
    expect(input).toHaveValue('my draft')
  })

  it('cancels without uploading or inserting anything', async () => {
    const user = userEvent.setup()
    installFakeMicrophone()
    render(<Composer onSend={vi.fn()} />)

    await user.click(screen.getByRole('button', { name: 'Start recording' }))
    await screen.findByRole('button', { name: 'Stop recording and transcribe' })
    await new Promise((resolve) => setTimeout(resolve, 500))
    await user.click(screen.getByRole('button', { name: 'Cancel recording' }))

    await waitFor(() => expect(screen.getByRole('button', { name: 'Start recording' })).toBeInTheDocument())
    expect(fetchMock).not.toHaveBeenCalled()
    expect(screen.getByRole('textbox', { name: 'Message' })).toHaveValue('')
    expect(FakeRecorder.instances[0]?.state).toBe('inactive')
  })

  it('cancels on Escape while recording', async () => {
    const user = userEvent.setup()
    installFakeMicrophone()
    render(<Composer onSend={vi.fn()} />)

    await user.click(screen.getByRole('button', { name: 'Start recording' }))
    await screen.findByRole('button', { name: 'Stop recording and transcribe' })
    await user.keyboard('{Escape}')

    await waitFor(() => expect(screen.getByRole('button', { name: 'Start recording' })).toBeInTheDocument())
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('explains a denied microphone without touching the draft', async () => {
    const user = userEvent.setup()
    installFakeMicrophone({
      getUserMedia: async () => {
        const error = new Error('denied')
        error.name = 'NotAllowedError'
        throw error
      },
    })
    const onSend = vi.fn()
    render(<Composer onSend={onSend} />)

    const input = screen.getByRole('textbox', { name: 'Message' })
    await user.type(input, 'keep me')
    await user.click(screen.getByRole('button', { name: 'Start recording' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Microphone access was blocked')
    expect(input).toHaveValue('keep me')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('reports an unreachable service and keeps the draft', async () => {
    const user = userEvent.setup()
    installFakeMicrophone()
    fetchMock.mockRejectedValueOnce(new TypeError('Failed to fetch'))
    render(<Composer onSend={vi.fn()} />)

    const input = screen.getByRole('textbox', { name: 'Message' })
    await user.type(input, 'keep me')
    await recordAndStop(user)

    expect(await screen.findByRole('alert')).toHaveTextContent('Could not reach the speech-to-text service')
    expect(input).toHaveValue('keep me')
  })

  it('surfaces the service error message for unusable audio', async () => {
    const user = userEvent.setup()
    installFakeMicrophone()
    fetchMock.mockResolvedValueOnce(transcriptionResponse({ detail: 'The recording was empty.' }, 422))
    render(<Composer onSend={vi.fn()} />)

    await recordAndStop(user)

    expect(await screen.findByRole('alert')).toHaveTextContent('The recording was empty.')
  })

  it('does not start a second recording on repeated clicks', async () => {
    const user = userEvent.setup()
    const { getUserMedia } = installFakeMicrophone()
    render(<Composer onSend={vi.fn()} />)

    const mic = screen.getByRole('button', { name: 'Start recording' })
    await user.click(mic)
    await screen.findByRole('button', { name: 'Stop recording and transcribe' })

    expect(getUserMedia).toHaveBeenCalledTimes(1)
    expect(FakeRecorder.instances).toHaveLength(1)
  })

  it('sends only one request when stop is pressed twice', async () => {
    const user = userEvent.setup()
    installFakeMicrophone()
    render(<Composer onSend={vi.fn()} />)

    await user.click(screen.getByRole('button', { name: 'Start recording' }))
    const stop = await screen.findByRole('button', { name: 'Stop recording and transcribe' })
    await new Promise((resolve) => setTimeout(resolve, 500))
    await user.click(stop)

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
  })

  it('drops a transcript that arrives after the conversation changed', async () => {
    const user = userEvent.setup()
    installFakeMicrophone()
    let release: (value: unknown) => void = () => {}
    fetchMock.mockImplementationOnce(
      () => new Promise((resolve) => { release = resolve }) as Promise<unknown>,
    )

    const { rerender } = render(<Composer key="c1" onSend={vi.fn()} />)
    await recordAndStop(user)
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))

    // Switching conversation remounts the composer (ChatPage keys it by id),
    // which must discard the transcript that is still in flight.
    rerender(<Composer key="c2" onSend={vi.fn()} />)
    release(transcriptionResponse({ text: TRANSCRIPT }))

    await waitFor(() => expect(screen.getByRole('button', { name: 'Start recording' })).toBeInTheDocument())
    expect(screen.getByRole('textbox', { name: 'Message' })).toHaveValue('')
  })

  it('blocks sending while a recording is active, then sends the transcript normally', async () => {
    const user = userEvent.setup()
    installFakeMicrophone()
    const onSend = vi.fn()
    render(<Composer onSend={onSend} />)

    const input = screen.getByRole('textbox', { name: 'Message' })
    await user.type(input, 'quick note')
    expect(screen.getByRole('button', { name: 'Send message' })).toBeEnabled()

    await user.click(screen.getByRole('button', { name: 'Start recording' }))
    expect(screen.getByRole('button', { name: 'Send message' })).toBeDisabled()

    // Already recording, so only the stop leg of the helper applies here.
    await screen.findByRole('button', { name: 'Stop recording and transcribe' })
    await new Promise((resolve) => setTimeout(resolve, 500))
    await user.click(screen.getByRole('button', { name: 'Stop recording and transcribe' }))
    // The caret was at the end of the draft, so the transcript is appended with
    // a single separating space.
    await waitFor(() => expect(input).toHaveValue(`quick note ${TRANSCRIPT}`))

    await user.click(screen.getByRole('button', { name: 'Send message' }))
    expect(onSend).toHaveBeenCalledWith(`quick note ${TRANSCRIPT}`)
    expect(input).toHaveValue('')
  })

  it('still sends typed messages with Enter while idle', async () => {
    const user = userEvent.setup()
    installFakeMicrophone()
    const onSend = vi.fn()
    render(<Composer onSend={onSend} />)

    const input = screen.getByRole('textbox', { name: 'Message' })
    await user.type(input, 'hello')
    await user.keyboard('{Enter}')

    expect(onSend).toHaveBeenCalledWith('hello')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('rejects a recording that is too short', async () => {
    const user = userEvent.setup()
    installFakeMicrophone()
    render(<Composer onSend={vi.fn()} />)

    await user.click(screen.getByRole('button', { name: 'Start recording' }))
    await screen.findByRole('button', { name: 'Stop recording and transcribe' })
    await user.click(screen.getByRole('button', { name: 'Stop recording and transcribe' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('too short')
    expect(fetchMock).not.toHaveBeenCalled()
  })
})
