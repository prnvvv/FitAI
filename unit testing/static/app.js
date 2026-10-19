/* Recording UI for the STT proof of concept.
   Flow: mic -> record -> stop -> transcribe -> insert into the textarea. */

const els = {
  input: document.getElementById('message-input'),
  mic: document.getElementById('mic-button'),
  micLabel: document.getElementById('mic-button-label'),
  stop: document.getElementById('stop-button'),
  clear: document.getElementById('clear-button'),
  send: document.getElementById('send-button'),
  recording: document.getElementById('recording-indicator'),
  timer: document.getElementById('recording-timer'),
  transcribing: document.getElementById('transcribing-indicator'),
  error: document.getElementById('error-message'),
  meta: document.getElementById('transcript-meta'),
  service: document.getElementById('service-status'),
  outgoing: document.getElementById('outgoing-list'),
}

const state = { stream: null, recorder: null, chunks: [], startedAt: 0, tick: null, busy: false, cancelled: false }

// Granite Speech 5.0 TurboCTC wants 16 kHz mono. `MediaRecorder` only produces
// webm/opus or mp4, so the clip is decoded and resampled here and uploaded as
// plain PCM WAV — that keeps the server free of an ffmpeg dependency.
const TARGET_SAMPLE_RATE = 16000

async function blobToWav(blob) {
  const decoded = await new AudioContext().decodeAudioData(await blob.arrayBuffer())
  const frames = Math.max(1, Math.round((decoded.duration * TARGET_SAMPLE_RATE)))
  const offline = new OfflineAudioContext(1, frames, TARGET_SAMPLE_RATE)
  const source = offline.createBufferSource()
  source.buffer = decoded
  source.connect(offline.destination)
  source.start()
  const rendered = await offline.startRendering()

  const mono = rendered.getChannelData(0)
  const buffer = new ArrayBuffer(44 + mono.length * 2)
  const view = new DataView(buffer)
  const ascii = (offset, text) => [...text].forEach((char, i) => view.setUint8(offset + i, char.charCodeAt(0)))
  ascii(0, 'RIFF')
  view.setUint32(4, 36 + mono.length * 2, true)
  ascii(8, 'WAVEfmt ')
  view.setUint32(16, 16, true) // PCM header size
  view.setUint16(20, 1, true) // PCM
  view.setUint16(22, 1, true) // mono
  view.setUint32(24, TARGET_SAMPLE_RATE, true)
  view.setUint32(28, TARGET_SAMPLE_RATE * 2, true) // byte rate
  view.setUint16(32, 2, true) // block align
  view.setUint16(34, 16, true) // bits per sample
  ascii(36, 'data')
  view.setUint32(40, mono.length * 2, true)
  for (let i = 0; i < mono.length; i += 1) {
    const clamped = Math.max(-1, Math.min(1, mono[i]))
    view.setInt16(44 + i * 2, clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff, true)
  }
  return { blob: new Blob([buffer], { type: 'audio/wav' }), duration: rendered.duration }
}

function setError(message) {
  els.error.textContent = message || ''
  els.error.hidden = !message
}

function setBusy(busy) {
  state.busy = busy
  els.mic.disabled = busy
  els.stop.disabled = busy || !state.recorder
  els.send.disabled = busy
  els.clear.disabled = busy
  els.input.readOnly = busy && !state.recorder
}

function preferredMimeType() {
  const candidates = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg;codecs=opus']
  return candidates.find((type) => window.MediaRecorder?.isTypeSupported?.(type)) || ''
}

async function refreshStatus() {
  try {
    const response = await fetch('/api/status')
    const status = await response.json()
    if (status.state === 'ready') {
      els.service.dataset.state = 'ready'
      els.service.textContent = `Model ready — ${status.model_id} on ${status.device} (16 kHz, loaded in ${status.load_seconds}s)`
    } else if (status.state === 'error') {
      els.service.dataset.state = 'error'
      els.service.textContent = `Model failed to load: ${status.error}`
      setError(`The speech model could not be loaded: ${status.error}`)
    } else {
      els.service.dataset.state = 'loading'
      els.service.textContent = `Loading ${status.model_id} (${status.state}) — this happens once, on first run.`
    }
  } catch (error) {
    els.service.dataset.state = 'error'
    els.service.textContent = 'The transcription service is not reachable.'
  }
}

async function startRecording() {
  setError('')
  els.meta.textContent = ''
  if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
    setError('This browser does not support MediaRecorder. Use a current Chrome, Edge, Firefox or Safari.')
    return
  }
  try {
    state.stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
    })
  } catch (error) {
    setError(
      error?.name === 'NotAllowedError'
        ? 'Microphone permission was denied. Allow it in the browser and try again.'
        : `Could not open the microphone: ${error?.message || error}`,
    )
    return
  }

  const mimeType = preferredMimeType()
  state.chunks = []
  state.recorder = new MediaRecorder(state.stream, mimeType ? { mimeType } : undefined)
  state.recorder.ondataavailable = (event) => {
    if (event.data && event.data.size > 0) state.chunks.push(event.data)
  }
  state.recorder.onstop = () => void handleRecordingStopped()
  state.recorder.start()

  state.startedAt = Date.now()
  state.tick = setInterval(() => {
    els.timer.textContent = `${((Date.now() - state.startedAt) / 1000).toFixed(1)}s`
  }, 100)

  els.recording.hidden = false
  els.mic.setAttribute('aria-pressed', 'true')
  els.micLabel.textContent = 'Recording'
  els.stop.disabled = false
  els.clear.disabled = false
}

function stopRecording() {
  if (state.recorder && state.recorder.state !== 'inactive') state.recorder.stop()
}

function releaseStream() {
  clearInterval(state.tick)
  state.tick = null
  state.stream?.getTracks().forEach((track) => track.stop())
  state.stream = null
  els.recording.hidden = true
  els.mic.setAttribute('aria-pressed', 'false')
  els.micLabel.textContent = 'Record'
}

async function handleRecordingStopped() {
  const cancelled = state.cancelled
  const blob = new Blob(state.chunks, { type: state.recorder?.mimeType || 'audio/webm' })
  const seconds = (Date.now() - state.startedAt) / 1000

  state.recorder = null
  state.chunks = []
  state.cancelled = false
  releaseStream()
  els.stop.disabled = true

  if (cancelled) {
    // "Clear" during a recording discards the clip without transcribing it.
    setError('')
    els.meta.textContent = ''
    return
  }
  if (blob.size === 0 || seconds < 0.3) {
    setError('That recording was too short. Hold the button and speak for at least half a second.')
    return
  }

  els.transcribing.hidden = false
  setBusy(true)
  const startedAt = Date.now()
  try {
    // Normalise to 16 kHz mono WAV in the browser; fall back to the raw clip
    // (the server then needs ffmpeg) if the browser cannot decode it.
    let payloadBlob = blob
    let filename = `recording.${blob.type.includes('mp4') ? 'm4a' : blob.type.includes('ogg') ? 'ogg' : 'webm'}`
    let sourceFormat = 'webm/opus'
    try {
      const wav = await blobToWav(blob)
      payloadBlob = wav.blob
      filename = 'recording.wav'
      sourceFormat = 'wav 16 kHz mono (browser)'
    } catch (decodeError) {
      console.warn('Browser-side WAV conversion failed, uploading the raw clip.', decodeError)
    }

    const body = new FormData()
    body.append('file', payloadBlob, filename)
    const response = await fetch('/api/transcribe', { method: 'POST', body })
    const payload = await response.json().catch(() => ({}))
    if (!response.ok) {
      throw new Error(payload.detail || `Transcription failed with HTTP ${response.status}`)
    }
    if (payload.text) {
      // Insert where the caret is, so the transcript can be edited before sending.
      const start = els.input.selectionStart ?? els.input.value.length
      const end = els.input.selectionEnd ?? els.input.value.length
      els.input.value = `${els.input.value.slice(0, start)}${payload.text}${els.input.value.slice(end)}`
      els.input.focus()
      els.input.setSelectionRange(start + payload.text.length, start + payload.text.length)
    } else {
      setError(payload.warning || 'The model returned an empty transcript. Try again, or type the message.')
    }
    els.meta.textContent = [
      `${seconds.toFixed(1)}s of audio`,
      payload.audio ? `${payload.audio.original_sample_rate} Hz ${payload.audio.source_format}` : sourceFormat,
      payload.model ? `${payload.model.model_id} on ${payload.model.device}` : '',
      `${((Date.now() - startedAt) / 1000).toFixed(1)}s to transcribe`,
    ]
      .filter(Boolean)
      .join(' · ')
  } catch (error) {
    setError(error?.message || 'Transcription failed.')
  } finally {
    els.transcribing.hidden = true
    setBusy(false)
  }
}

function clearAll() {
  const wasRecording = Boolean(state.recorder)
  state.cancelled = wasRecording
  if (wasRecording && state.recorder.state !== 'inactive') state.recorder.stop()
  state.recorder = null
  state.chunks = []
  releaseStream()
  els.input.value = ''
  els.meta.textContent = ''
  setError('')
  setBusy(false)
}

function sendLocally() {
  const text = els.input.value.trim()
  if (!text) {
    setError('Type or record something first.')
    return
  }
  const item = document.createElement('li')
  item.className = 'outgoing__item'
  item.textContent = text
  els.outgoing.appendChild(item)
  els.input.value = ''
  els.meta.textContent = ''
  setError('')
}

els.mic.addEventListener('click', () => void startRecording())
els.stop.addEventListener('click', stopRecording)
els.clear.addEventListener('click', clearAll)
els.send.addEventListener('click', sendLocally)
els.input.addEventListener('keydown', (event) => {
  if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') sendLocally()
})

void refreshStatus()
setInterval(() => {
  if (els.service.dataset.state !== 'ready' && !state.busy) void refreshStatus()
}, 5000)