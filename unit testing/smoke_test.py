# Real-model smoke test for IBM Granite Speech 5.0 TurboCTC.
#
# Kept out of the automated suite on purpose: it downloads ~900 MB of weights
# and needs torch/transformers installed. It never fabricates a transcript —
# if the model cannot run here it fails loudly and prints what is missing.
#
#   python smoke_test.py --audio path/to/clip.wav
#
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from audio_utils import AudioValidationError, decode_audio, is_silent, rms  # noqa: E402
from speech_service import ModelLoadError, SpeechService  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio", required=True, help="WAV (or ffmpeg-decodable) file to transcribe")
    parser.add_argument("--device", default=None, help="auto | cpu | cuda (default: STT_DEVICE or auto)")
    args = parser.parse_args()

    path = Path(args.audio)
    if not path.is_file():
        print(f"Audio file not found: {path}")
        return 2

    data = path.read_bytes()
    try:
        audio = decode_audio(data, path.name)
    except AudioValidationError as exc:
        print(f"Audio rejected: {exc}")
        return 2

    print(f"Audio   : {path.name}")
    print(f"  format: {audio.source_format} ({audio.original_sample_rate} Hz) -> {audio.sample_rate} Hz mono")
    print(f"  length: {audio.duration_s:.2f}s, rms={rms(audio.samples):.5f}")
    if is_silent(audio.samples):
        print("  note  : this clip looks like silence; the transcript will probably be empty.")

    service = SpeechService(device=args.device)
    print(f"Model   : {service.model_id}")
    print("Loading (first run downloads ~900 MB)...")
    started = time.perf_counter()
    try:
        service.load()
    except ModelLoadError as exc:
        print(f"Model failed to load: {exc}")
        return 1
    print(f"Loaded in {time.perf_counter() - started:.1f}s on {service.status.device}")

    started = time.perf_counter()
    result = service.transcribe(audio.samples, audio.sample_rate)
    print(f"Transcribed in {time.perf_counter() - started:.2f}s")
    print(f"Transcript: {result.text!r}")
    if not result.text:
        print("Warning: the model returned an empty transcript. Accuracy is not guaranteed; edit before sending.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())