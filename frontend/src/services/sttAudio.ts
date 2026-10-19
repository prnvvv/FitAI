/**
 * Browser-side audio preparation for speech-to-text.
 *
 * MediaRecorder only produces compressed containers (webm/opus in Chromium,
 * mp4 in Safari). Granite Speech 5.0 TurboCTC expects 16 kHz mono, so the clip
 * is decoded and resampled here and uploaded as plain PCM WAV. The service can
 * decode the compressed original too (it falls back to PyAV), so a browser that
 * refuses to decode its own recording still works — just slower.
 */

/** Sample rate the model expects (`preprocessor_config.json`). */
export const TARGET_SAMPLE_RATE = 16_000

/** MIME types we prefer, best first, for the current browser. */
export function preferredAudioMimeType(): string {
  if (typeof MediaRecorder === 'undefined') return ''
  const candidates = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg;codecs=opus']
  return candidates.find((type) => MediaRecorder.isTypeSupported(type)) ?? ''
}

/** File name matching the container the browser actually produced. */
export function recordingFilename(mimeType: string): string {
  if (mimeType.includes('mp4')) return 'recording.m4a'
  if (mimeType.includes('ogg')) return 'recording.ogg'
  return 'recording.webm'
}

async function decodeBlob(blob: Blob): Promise<AudioBuffer> {
  const AudioCtx = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
  if (!AudioCtx) throw new Error('this browser has no Web Audio support')
  const ctx = new AudioCtx()
  // An autoplay-policy-suspended context can fail to decode; try to wake it.
  if (ctx.state === 'suspended') {
    try {
      await ctx.resume()
    } catch {
      /* decoding generally still works while suspended */
    }
  }
  const buffer = await blob.arrayBuffer()
  try {
    const pending = ctx.decodeAudioData(buffer)
    // Older Safari resolves through callbacks and returns undefined.
    if (pending && typeof pending.then === 'function') return await pending
    return await new Promise<AudioBuffer>((resolve, reject) => ctx.decodeAudioData(buffer, resolve, reject))
  } finally {
    try {
      ctx.close()
    } catch {
      /* ignore */
    }
  }
}

function writeWavHeader(view: DataView, dataBytes: number): void {
  const ascii = (offset: number, text: string) =>
    [...text].forEach((char, index) => view.setUint8(offset + index, char.charCodeAt(0)))
  ascii(0, 'RIFF')
  view.setUint32(4, 36 + dataBytes, true)
  ascii(8, 'WAVEfmt ')
  view.setUint32(16, 16, true) // PCM header size
  view.setUint16(20, 1, true) // PCM
  view.setUint16(22, 1, true) // mono
  view.setUint32(24, TARGET_SAMPLE_RATE, true)
  view.setUint32(28, TARGET_SAMPLE_RATE * 2, true) // byte rate
  view.setUint16(32, 2, true) // block align
  view.setUint16(34, 16, true) // bits per sample
  ascii(36, 'data')
  view.setUint32(40, dataBytes, true)
}

export interface PreparedAudio {
  blob: Blob
  filename: string
  /** Set when the browser could not convert and the original is being sent. */
  conversionNote: string | null
}

/** Converts a recording to 16 kHz mono WAV, falling back to the original clip. */
export async function prepareAudioForUpload(blob: Blob): Promise<PreparedAudio> {
  const original = recordingFilename(blob.type)
  try {
    const decoded = await decodeBlob(blob)
    const frames = Math.max(1, Math.round(decoded.duration * TARGET_SAMPLE_RATE))

    let mono: Float32Array
    if (typeof OfflineAudioContext !== 'undefined') {
      const offline = new OfflineAudioContext(1, frames, TARGET_SAMPLE_RATE)
      const source = offline.createBufferSource()
      source.buffer = decoded
      source.connect(offline.destination)
      source.start()
      mono = (await offline.startRendering()).getChannelData(0)
    } else {
      // Nearest-neighbour resample when OfflineAudioContext is missing.
      const data = decoded.getChannelData(0)
      mono = new Float32Array(frames)
      for (let index = 0; index < frames; index += 1) {
        mono[index] = data[Math.min(data.length - 1, Math.round((index / frames) * data.length))]
      }
    }

    const wav = new ArrayBuffer(44 + mono.length * 2)
    const view = new DataView(wav)
    writeWavHeader(view, mono.length * 2)
    for (let index = 0; index < mono.length; index += 1) {
      const clamped = Math.max(-1, Math.min(1, mono[index]))
      view.setInt16(44 + index * 2, clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff, true)
    }
    return { blob: new Blob([wav], { type: 'audio/wav' }), filename: 'recording.wav', conversionNote: null }
  } catch (error) {
    const reason = error instanceof Error ? error.message : String(error)
    return {
      blob,
      filename: original,
      conversionNote: `Browser could not convert the clip (${reason}); sent the original ${original}.`,
    }
  }
}