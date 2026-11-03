"""Local stand-ins for the external providers, used ONLY by deployment smoke tests.

One HTTP server emulating, on a single port:

* ``POST /embed``                         HuggingFace-style feature extraction (384-d vectors)
* ``POST /stt/v1/audio/transcriptions``   OpenAI-compatible transcription
* ``POST|GET|DELETE /storage/v1/object/<bucket>/<key>``  Supabase Storage REST
* ``POST /openai/v1/chat/completions``    Groq (OpenAI-compatible) chat completion

These are deterministic fakes that let the real containers run end-to-end without
credentials. They prove the services' own behaviour (memory, restart recovery,
wiring) - NOT the behaviour or quality of the real providers.

    python mock_providers.py 8801 [embed_delay_seconds]
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DIM = 384
STORE: dict[str, bytes] = {}
STATS = {
    "embed_requests": 0,
    "embed_texts": 0,
    "stt_requests": 0,
    "stt_bytes": 0,
    "chat_requests": 0,
}
LOCK = threading.Lock()
EMBED_DELAY = float(sys.argv[2]) if len(sys.argv) > 2 else 0.0


def embed(text: str) -> list[float]:
    vec = [0.0] * DIM
    for word in text.lower().split():
        vec[int(hashlib.sha256(word.encode()).hexdigest(), 16) % DIM] += 1.0
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args) -> None:  # noqa: D401, ANN002
        pass

    def _body(self) -> bytes:
        remaining = int(self.headers.get("Content-Length") or 0)
        chunks = []
        while remaining > 0:
            part = self.rfile.read(min(remaining, 1 << 20))
            if not part:
                break
            chunks.append(part)
            remaining -= len(part)
        return b"".join(chunks)

    def _send(self, status: int, payload: bytes, ctype: str = "application/json") -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _json(self, status: int, obj: object) -> None:
        self._send(status, json.dumps(obj).encode())

    def do_POST(self) -> None:  # noqa: N802
        body = self._body()
        path = self.path
        if path == "/embed":
            texts = json.loads(body)["inputs"]
            time.sleep(EMBED_DELAY)
            with LOCK:
                STATS["embed_requests"] += 1
                STATS["embed_texts"] += len(texts)
            return self._json(200, [embed(t) for t in texts])
        if path == "/stt/v1/audio/transcriptions":
            with LOCK:
                STATS["stt_requests"] += 1
                STATS["stt_bytes"] += len(body)
            return self._json(200, {"text": "mock transcript"})
        if path.startswith("/storage/v1/object/"):
            if self.headers.get("x-upsert") == "false" and path in STORE:
                return self._json(409, {"error": "Duplicate"})
            STORE[path] = body
            return self._json(200, {"Key": path})
        if path == "/openai/v1/chat/completions":
            with LOCK:
                STATS["chat_requests"] += 1
            return self._json(
                200,
                {
                    "id": "mock",
                    "object": "chat.completion",
                    "created": int(time.time()),
                    "model": "mock",
                    "choices": [
                        {
                            "index": 0,
                            "finish_reason": "stop",
                            "message": {"role": "assistant", "content": "Mock coach reply."},
                        }
                    ],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                },
            )
        self._json(404, {"error": "unknown"})

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/stats":
            return self._json(200, {**STATS, "objects": len(STORE)})
        if self.path in STORE:
            return self._send(200, STORE[self.path], "application/octet-stream")
        self._json(404, {"error": "not found"})

    def do_DELETE(self) -> None:  # noqa: N802
        STORE.pop(self.path, None)
        self._json(200, {})


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8801
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"mock providers listening on :{port}", flush=True)
    server.serve_forever()
