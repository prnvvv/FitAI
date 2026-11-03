"""Check that the REMOTE embedding provider matches the LOCAL ONNX model.

Run this once, with real provider credentials, BEFORE cutting retrieval over to the
remote provider on top of vectors that were produced locally. It embeds a fixed set
of sentences with both and compares them:

* dimension must equal ``EMBEDDING_DIMENSION`` (384) for both;
* cosine similarity between the two embeddings of the same text must be >= --min-cosine
  (default 0.98) for every sentence.

If this fails, DO NOT migrate Chroma vectors as-is: re-embed the documents with the
remote provider instead (the migration script copies vectors verbatim).

    EMBEDDING_API_URL=... EMBEDDING_API_KEY=... python scripts/verify_embedding_parity.py
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

SAMPLES = [
    "Progressive overload means gradually increasing training stress over time.",
    "How much protein should I eat to build muscle?",
    "A deadlift trains the hamstrings, glutes and lower back.",
    "Marathon training relies on long, slow aerobic runs.",
    "Sleep seven to nine hours for better recovery.",
    "I have a sore left knee, what mobility work helps?",
]


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    return dot / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--min-cosine", type=float, default=0.98)
    args = parser.parse_args()

    from app.core.config import settings
    from app.rag.embeddings import get_remote_embedder, repair_embedding_cache

    repair_embedding_cache()
    from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

    local = [list(map(float, v)) for v in DefaultEmbeddingFunction()(SAMPLES)]
    remote = get_remote_embedder().embed(SAMPLES)

    failures = 0
    for text, a, b in zip(SAMPLES, local, remote, strict=True):
        sim = cosine(a, b)
        ok = len(a) == len(b) == settings.embedding_dimension and sim >= args.min_cosine
        failures += 0 if ok else 1
        print(f"{'OK  ' if ok else 'FAIL'} cos={sim:.4f} dim={len(a)}/{len(b)}  {text[:50]}")
    print("PARITY OK" if not failures else f"PARITY FAILED ({failures} sentence(s))")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
