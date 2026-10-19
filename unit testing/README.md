# Speech-to-text proof of concept (isolated)

An isolated experiment that proves **record → transcribe → insert** for the FitAI
chat composer, using
[`ibm-granite/granite-speech-5.0-470m-turboctc`](https://huggingface.co/ibm-granite/granite-speech-5.0-470m-turboctc).

> **Nothing here is wired into FitAI.** This folder has its own virtual
> environment, its own dependencies and its own `.env`. No FitAI frontend or
> backend file, API, route, schema or manifest is touched, and the page never
> calls an LLM or the FitAI backend.

## 1. Layout

```text
unit testing/
├── README.md
├── requirements.txt
├── .env.example
├── .gitignore
├── app.py                     # FastAPI app: /api/status, /api/transcribe, static page
├── speech_service.py          # Granite loading + inference, load once, reuse
├── audio_utils.py             # decode, downmix, resample to 16 kHz, silence checks
├── smoke_test.py              # optional real-model run (separate from pytest)
├── static/
│   ├── index.html             # composer + mic + stop + clear + send
│   ├── app.js                 # MediaRecorder flow and text insertion
│   └── styles.css
├── tests/
│   ├── conftest.py            # fakes for the model — no torch, no download
│   ├── test_audio_utils.py
│   ├── test_transcription.py
│   └── test_api.py
└── recordings/                # scratch space (git-ignored)
```

## 2. Inference method and why

The model card states Granite Speech 5.0 TurboCTC is **natively supported in
`transformers>=5.16.0`** and documents this exact procedure, which is what
`speech_service.py` implements:

```python
processor = AutoProcessor.from_pretrained(model_id)
model = AutoModelForCTC.from_pretrained(model_id, device_map="auto")
inputs = processor(samples, sampling_rate=16000, device=model.device)
inputs.to(model.device, dtype=model.dtype)
outputs = model.generate(**inputs)
text = processor.batch_decode(outputs, skip_special_tokens=True)
```

The generic `pipeline("automatic-speech-recognition", ...)` shortcut listed on the
model page is deliberately **not** used: the documented native path keeps the
log-mel front-end on the accelerator (`device=model.device`) and is the
procedure the model authors test against. If the native processor class is not
available in the installed `transformers`, the loader falls back to the
repository's own `processing_ctc_conformer.py` via `trust_remote_code=True`.

The model is a CTC model: inference is greedy and non-autoregressive, so
"turbo" refers to speed, not streaming. Recording is therefore stop-then-
transcribe, not partial streaming.

### API key

`HUGGINGFACE_API_KEY` is **not required** — the repository is public
(`gated: false`). The variable is read if present (faster/authenticated
downloads) and is never sent to the browser, printed or logged. The reference
token was stored in the git-ignored `backend/.env`; it also appears in the
task conversation in plaintext, so it should be rotated.

## 3. Requirements

| | |
|---|---|
| Python | 3.10+ (3.10.10 verified; `transformers` 5.x needs ≥3.10) |
| RAM | ~3 GB free for weights + activations (16 kHz audio is held in one piece) |
| GPU | optional. `device_map="auto"` uses CUDA when present; CPU-only works |
| Disk | ~0.9 GB for `model.safetensors` in the Hugging Face cache + ~2.5 GB for the CUDA torch wheel |
| ffmpeg | **optional.** Only needed if you upload a compressed file from outside the browser. The page converts recordings to 16 kHz mono WAV in the browser, so the normal flow needs no ffmpeg |

**`torchaudio` is required, and it must match your `torch` exactly.**
`GraniteSpeech5FeatureExtractor` builds its log-mel front-end with
`torchaudio.transforms.MelSpectrogram` / `torchaudio.functional.compute_deltas`,
so transformers raises *"requires the torchaudio library but it was not found"*
if it is missing. torchaudio only publishes wheels for the torch release it is
pinned to, and the latest pair is **2.9.1 / 2.9.1** — installing torch 2.10+
leaves you with a torch that has no matching torchaudio. `requirements.txt`
pins the working pair and the loader prints this hint when it trips.

Measured on this machine (CPU-only torch 2.9.1, 16 kHz mono):

| step | result |
|---|---|
| First load (900 MB download) | 529 s (network-bound), weights loaded in 1.9 s |
| Transcription of 33.6 s of 8 kHz speech | 7.1 s on CPU (~4.7× realtime) |

`recordings/jfk.wav` (a public-domain 8 kHz speech clip) is included locally for
re-running the smoke test; it is git-ignored.

## 4. Setup and run (Windows, PowerShell or bash)

```bash
cd "unit testing"
python -m venv .venv
.venv/Scripts/python -m pip install --upgrade pip
.venv/Scripts/python -m pip install -r requirements.txt

# Optional: copy .env.example to .env and fill in HUGGINGFACE_API_KEY
.venv/Scripts/python -m uvicorn app:app --host 127.0.0.1 --port 8077
```

macOS/Linux: replace `.venv/Scripts/python` with `.venv/bin/python`.

Then open <http://127.0.0.1:8077>.

Useful switches (env vars): `STT_DEVICE=cpu|cuda|auto`, `STT_MODEL_ID=...`,
`STT_EAGER_LOAD=0` (skip the background download and load on the first request
instead), `STT_PORT`.

### First run

The first start downloads ~900 MB of weights in a background thread. The page
shows `Loading … (loading)` until it is ready, then
`Model ready — ibm-granite/… on cuda`. The UI is usable while that happens; the
first transcription waits for the load to finish.

## 5. Tests

```bash
.venv/Scripts/python -m pytest -q
```

The suite never downloads the model and never needs an API key: the model,
processor and inference call are injected through `SpeechService(loader=…,
transcriber=…)`. It covers audio decoding/resampling/validation, silence, empty
transcripts, model-load and inference failures, the HTTP request/response
contract, the error page state, and a static contract check of the frontend
(recorder calls, `/api/transcribe` post, insertion into the textarea, and the
absence of any FitAI/Groq chat call).

### Real-model smoke test (separate, on demand)

```bash
.venv/Scripts/python -m pip install -r requirements.txt   # includes torch + transformers
.venv/Scripts/python smoke_test.py --audio path/to/clip.wav
```

It downloads the checkpoint, transcribes one clip and prints the transcript and
timings. It fails loudly (non-zero exit) if the model cannot load; it never
prints a fabricated result. Record a clip first with the page, or download any
short English WAV.

## 6. Manual microphone walkthrough

1. Start the server and open <http://127.0.0.1:8077>. The status line reports
   the model state.
2. Click **Record**. The browser asks for microphone permission — allow it.
   The button turns red, a pulsing dot and a live timer appear, and **Stop
   recording** becomes enabled.
3. Speak for a second or two.
4. Click **Stop recording**. The indicator disappears and a spinner
   ("Transcribing with Granite Speech…") appears while inference runs. Nothing
   is sent anywhere.
5. The recognised text is inserted **at the caret** in the message box. Read
   it, fix any mistakes — recognition is not perfect, especially with
   background noise, accents or unusual terms.
6. Click **Send** (or Ctrl/Cmd+Enter). The message is appended to the local
   "Composed messages" list and the box is cleared. This does **not** contact
   FitAI or any model.
7. **Clear** empties the box and discards an in-progress recording.
8. Error states you can reproduce: deny the microphone permission and the page
   shows a permission error; record <0.3 s and it reports a too-short
   recording; speak only silence and the service answers "No speech was
   detected".

Cleanup: stop the server, then delete `.venv/`, the Hugging Face cache
(`%USERPROFILE%\.cache\huggingface`) and `recordings/` — everything is outside
Git.

## 7. API

`GET /api/status`

```json
{ "state": "ready", "model_id": "ibm-granite/granite-speech-5.0-470m-turboctc",
  "device": "cuda:0", "sample_rate": 16000, "error": "", "requests": 3 }
```

`POST /api/transcribe` — `multipart/form-data`, field `file` (WAV preferred,
webm/ogg/mp4/mp3 also accepted when ffmpeg is installed).

```json
{ "text": "how many protein shakes should I drink after training",
  "audio": { "duration_s": 3.2, "sample_rate": 16000, "source_format": "wav",
             "original_sample_rate": 16000, "rms": 0.0812 },
  "model": { "model_id": "ibm-granite/granite-speech-5.0-470m-turboctc", "device": "cuda:0", "load_seconds": 4.3 },
  "warnings": [] }
```

| Status | Meaning |
|---|---|
| 200 | transcribed (empty `text` + `warning` when nothing was recognised or the clip was silent) |
| 413 | upload larger than 25 MB |
| 422 | empty, corrupt, too short (<0.3 s) or unsupported audio |
| 500 | inference failed |
| 503 | the model is not loaded / failed to load (dependencies missing, download failed, out of memory) |

## 8. Known limitations

- **Non-speech audio can produce words.** Verified with the real model: a 3.2 s
  pure 440 Hz tone (Chromium's fake microphone device) came back as
  `"thanks"`. CTC decoders emit the most likely token sequence for whatever
  they are fed, and an RMS silence check cannot catch this. A cheap
  spectral-flatness guard was measured and **rejected**: three real speech clips
  scored 0.0002 / 0.0003 / 0.0282 against 0.0000 for the tone — far too close to
  threshold safely without discarding valid speech. Treat every transcript as a
  draft: if the microphone picked up music, a tone or noise, read it before
  sending.
- English only; short-form speech (it was trained for short utterances, not
  meetings or dictation-length audio).
- The transcript comes back as lowercase text without punctuation or
  capitalisation — the model is a CTC/BPE system, so expect
  `"the birch canoe slid on the smooth planks"` rather than a punctuated
  sentence. Capitalise and punctuate before sending if that matters.
- Accuracy is not guaranteed. Proper nouns, numbers and noisy rooms are where
  errors show up, which is why the transcript lands in an editable box.
- English model, so non-English speech will transcribe poorly or not at all.
- The browser converts to 16 kHz mono WAV client-side; very long recordings are
  held in memory in the page and capped at 25 MB server-side.
- Inference is blocking inside a single worker; one request at a time, which is
  all this experiment needs.