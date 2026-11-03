"""Container smoke + memory + restart-recovery verification (local, disposable).

Runs the three real images with a 512 MB memory limit against a DISPOSABLE
pgvector Postgres and the fake providers in ``mock_providers.py``, then prints a
JSON report (peak RSS per scenario, restart-recovery result).

Prerequisites::

    docker build -f Dockerfile.core      -t fitai-core:test .
    docker build -f Dockerfile.stt       -t fitai-stt:test .
    docker build -f Dockerfile.documents -t fitai-documents:test .
    docker run -d --name fitai-pgvector-test -e POSTGRES_PASSWORD=test \
        -e POSTGRES_DB=fitai_test -p 54329:5432 pgvector/pgvector:pg16

    python scripts/deploy_smoke/run_smoke.py

DESTRUCTIVE to the target database: it DROPs the ``public`` schema of the database
named by ``--db-url`` (default: the disposable container above). Never point it at
a real database; it refuses any URL whose database name does not end in ``_test``.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
import time
import urllib.request
import uuid
from http.server import ThreadingHTTPServer
from pathlib import Path

import jwt
import psycopg2

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(Path(__file__).parent))
import mock_providers  # noqa: E402

from tests.pdf_factory import make_pdf  # noqa: E402

SECRET = "smoke-test-secret-smoke-test-secret-0123456789"
SUPABASE_URL = "https://smoke.supabase.co"
MOCK_PORT = 8801
HOST = "host.docker.internal"
MB = 1024 * 1024


def sh(*args: str, check: bool = True, timeout: int = 300) -> str:
    out = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if check and out.returncode != 0:
        raise RuntimeError(f"{' '.join(args)}\n{out.stdout}\n{out.stderr}")
    return (out.stdout + out.stderr).strip()


def token(user: str) -> str:
    return jwt.encode(
        {
            "sub": user,
            "aud": "authenticated",
            "iss": f"{SUPABASE_URL}/auth/v1",
            "exp": int(time.time()) + 3600,
            "email": "smoke@example.com",
        },
        SECRET,
        algorithm="HS256",
    )


def http(method: str, url: str, headers=None, data: bytes | None = None, timeout=60):
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:  # noqa: PERF203
        return exc.code, exc.read()


def multipart(filename: str, content_type: str, payload: bytes) -> tuple[bytes, str]:
    boundary = "----smoke" + uuid.uuid4().hex
    head = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
        f'filename="{filename}"\r\nContent-Type: {content_type}\r\n\r\n'
    ).encode()
    return (
        head + payload + f"\r\n--{boundary}--\r\n".encode(),
        f"multipart/form-data; boundary={boundary}",
    )


def mem(container: str) -> dict[str, float]:
    """PID 1 current/peak RSS (MB) and the container cgroup's own peak (MB)."""
    status = sh("docker", "exec", container, "sh", "-c", "grep -E 'VmRSS|VmHWM' /proc/1/status")
    vals = {ln.split(":")[0]: int(ln.split()[1]) / 1024 for ln in status.splitlines()}
    peak = sh(
        "docker",
        "exec",
        container,
        "sh",
        "-c",
        "cat /sys/fs/cgroup/memory.peak 2>/dev/null || cat /sys/fs/cgroup/memory/memory.max_usage_in_bytes",
    )
    return {
        "rss_mb": round(vals["VmRSS"], 1),
        "peak_rss_mb": round(vals["VmHWM"], 1),
        "cgroup_peak_mb": round(int(peak) / MB, 1),
    }


class Svc:
    def __init__(self, name: str, image: str, port: int, env: dict[str, str], db_url: str):
        self.name, self.image, self.port = name, image, port
        self.env = {
            "DATABASE_URL": db_url.replace("localhost", HOST),
            "CORS_ORIGINS": "https://app.example.com",
            "SUPABASE_URL": SUPABASE_URL,
            "SUPABASE_JWT_SECRET": SECRET,
            "LOG_LEVEL": "INFO",
            **env,
        }
        self.url = f"http://localhost:{port}"

    def start(self) -> None:
        sh("docker", "rm", "-f", self.name, check=False)
        args = [
            "docker",
            "run",
            "-d",
            "--name",
            self.name,
            "--memory",
            "512m",
            "--memory-swap",
            "512m",
            "--add-host",
            f"{HOST}:host-gateway",
            "-p",
            f"{self.port}:8000",
        ]
        for key, value in self.env.items():
            args += ["-e", f"{key}={value}"]
        sh(*args, self.image)
        self.wait()

    def wait(self, timeout: int = 90) -> None:
        end = time.time() + timeout
        while time.time() < end:
            try:
                if http("GET", f"{self.url}/health", timeout=3)[0] == 200:
                    return
            except OSError:
                pass
            time.sleep(1)
        raise RuntimeError(
            f"{self.name} did not become healthy:\n{sh('docker', 'logs', '--tail', '40', self.name)}"
        )

    def stop(self) -> None:
        sh("docker", "rm", "-f", self.name, check=False)


def db_query(db_url: str, sql: str, args=()):
    conn = psycopg2.connect(db_url.replace("+psycopg2", ""))
    try:
        with conn, conn.cursor() as cur:
            cur.execute(sql, args)
            return cur.fetchall() if cur.description else None
    finally:
        conn.close()


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--db-url", default="postgresql+psycopg2://postgres:test@localhost:54329/fitai_test"
    )
    p.add_argument("--pdf-pages", type=int, default=600)
    args = p.parse_args()
    db_name = args.db_url.rsplit("/", 1)[-1]
    if not db_name.endswith("_test"):
        raise SystemExit("Refusing to run: the database name must end in '_test'.")
    plain = args.db_url.replace("+psycopg2", "")
    report: dict[str, object] = {}

    # --- disposable database + migration through the image (the manual prod step)
    db_query(plain, "DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    sh(
        "docker",
        "run",
        "--rm",
        "--add-host",
        f"{HOST}:host-gateway",
        "-e",
        f"DATABASE_URL={args.db_url.replace('localhost', HOST)}",
        "-e",
        "ENVIRONMENT=development",
        "--entrypoint",
        "alembic",
        "fitai-core:test",
        "upgrade",
        "head",
    )
    report["migration_via_image"] = db_query(plain, "SELECT version_num FROM alembic_version")[0][0]

    # --- fake providers on the host
    mock_providers.EMBED_DELAY = 0.15
    server = ThreadingHTTPServer(("0.0.0.0", MOCK_PORT), mock_providers.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    mock = f"http://{HOST}:{MOCK_PORT}"

    embed_env = {
        "VECTOR_STORE_BACKEND": "pgvector",
        "EMBEDDING_PROVIDER": "remote",
        "EMBEDDING_API_URL": f"{mock}/embed",
        "EMBEDDING_API_KEY": "mock-key",
        "EMBEDDING_API_FORMAT": "hf",
        "EMBEDDING_DIMENSION": "384",
    }
    user = str(uuid.uuid4())
    auth = {"Authorization": f"Bearer {token(user)}"}

    # Seed the shared knowledge collection so chat retrieval has something to find.
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.rag.chunker import Chunk
    from app.rag.pg_vector_store import PgVectorStore
    from app.rag.vector_store import KNOWLEDGE_COLLECTION

    seed_engine = create_engine(args.db_url, future=True)
    seeder = PgVectorStore(
        embedding_function=lambda texts: [mock_providers.embed(t) for t in texts],
        session_factory=sessionmaker(bind=seed_engine, expire_on_commit=False),
        dimension=384,
    )
    seeder.add_chunks(
        KNOWLEDGE_COLLECTION,
        [
            Chunk(f"k{i}", t, {"doc_id": f"k{i}", "source": "kb.md", "page": -1, "chunk_index": 0})
            for i, t in enumerate(
                [
                    "A good squat routine uses progressive overload with three sets of five reps.",
                    "Protein supports muscle recovery after resistance training.",
                    "Sleep seven to nine hours per night for recovery.",
                ]
            )
        ],
    )
    seed_engine.dispose()
    before = json.loads(http("GET", f"http://localhost:{MOCK_PORT}/stats")[1])

    # ============================= CORE =====================================
    core = Svc(
        "smoke-core",
        "fitai-core:test",
        18001,
        {
            "ENVIRONMENT": "production",
            "FITAI_SERVICE": "core",
            "GROQ_API_KEY": "mock",
            "GROQ_BASE_URL": mock,
            "SERVE_DOCUMENTS_ROUTES": "false",
            "SERVE_STT_ROUTES": "false",
            "CONTINUITY_ENABLED": "true",
            "GUARD_CLASSIFIER_ENABLED": "false",
            "PROMPT_GUARD_ENABLED": "false",
            **embed_env,
        },
        args.db_url,
    )
    core.start()
    time.sleep(3)
    core_report = {
        "startup": mem("smoke-core"),
        "health": http("GET", f"{core.url}/health")[0],
        "ready": http("GET", f"{core.url}/health/ready")[0],
        "unauthenticated_chat": http(
            "POST",
            f"{core.url}/api/v1/chat",
            data=b"{}",
            headers={"Content-Type": "application/json"},
        )[0],
        "documents_route_absent": http("GET", f"{core.url}/api/v1/documents", headers=auth)[0],
        "stt_route_absent": http("GET", f"{core.url}/api/v1/stt/status", headers=auth)[0],
    }
    chat_codes = []
    for i in range(8):
        body = json.dumps({"message": f"What is a good squat routine? ({i})"}).encode()
        code, resp = http(
            "POST",
            f"{core.url}/api/v1/chat",
            data=body,
            timeout=120,
            headers={**auth, "Content-Type": "application/json"},
        )
        chat_codes.append(code)
    core_report["chat_status_codes"] = chat_codes
    core_report["chat_last_response"] = resp[:200].decode(errors="replace")
    after = json.loads(http("GET", f"http://localhost:{MOCK_PORT}/stats")[1])
    core_report["embed_requests_from_chat"] = after["embed_requests"] - before["embed_requests"]
    core_report["llm_requests_from_chat"] = after["chat_requests"]
    logs = sh("docker", "logs", "smoke-core", check=False)
    core_report["traceback_lines_in_log"] = logs.count("Traceback")
    core_report["after_requests"] = mem("smoke-core")
    report["core"] = core_report
    core.stop()

    # ============================== STT =====================================
    stt = Svc(
        "smoke-stt",
        "fitai-stt:test",
        18002,
        {
            "ENVIRONMENT": "production",
            "FITAI_SERVICE": "stt",
            "STT_PROVIDER": "remote",
            "STT_REMOTE_URL": f"{mock}/stt/v1/audio/transcriptions",
            "STT_REMOTE_API_KEY": "mock-key",
            "STT_REMOTE_MODEL": "mock",
            "STT_MAX_UPLOAD_MB": "10",
        },
        args.db_url,
    )
    stt.start()
    time.sleep(2)
    stt_report = {
        "startup": mem("smoke-stt"),
        "status": json.loads(http("GET", f"{stt.url}/api/v1/stt/status", headers=auth)[1]),
    }
    audio = b"\x1a\x45\xdf\xa3" + b"\x00" * (9 * MB + 700_000)  # ~9.7 MB, just under the limit
    body, ctype = multipart("clip.webm", "audio/webm", audio)
    codes = [
        http(
            "POST",
            f"{stt.url}/api/v1/stt/transcribe",
            data=body,
            headers={**auth, "Content-Type": ctype},
            timeout=120,
        )[0]
        for _ in range(3)
    ]
    big = b"\x1a\x45\xdf\xa3" + b"\x00" * (11 * MB)
    body2, ctype2 = multipart("big.webm", "audio/webm", big)
    stt_report["transcribe_codes"] = codes
    stt_report["oversize_code"] = http(
        "POST",
        f"{stt.url}/api/v1/stt/transcribe",
        data=body2,
        headers={**auth, "Content-Type": ctype2},
        timeout=120,
    )[0]
    stt_report["after_requests"] = mem("smoke-stt")
    report["stt"] = stt_report
    stt.stop()

    # ============================ DOCUMENTS =================================
    docs_env = {
        "ENVIRONMENT": "production",
        "FITAI_SERVICE": "documents",
        "INGESTION_MODE": "jobs",
        "INGESTION_PAGES_PER_BATCH": "5",
        "INGESTION_LEASE_SECONDS": "15",
        "INGESTION_POLL_SECONDS": "1",
        "DOCUMENT_STORAGE_BACKEND": "supabase",
        "SUPABASE_URL": mock,
        "SUPABASE_SERVICE_ROLE_KEY": "mock-service-key",
        "SUPABASE_STORAGE_BUCKET": "fitai-documents",
        "MAX_UPLOAD_SIZE_MB": "10",
        **embed_env,
    }
    docs = Svc("smoke-docs", "fitai-documents:test", 18003, docs_env, args.db_url)
    # SUPABASE_URL doubles as the JWT issuer base: re-issue the token for the mock URL.
    docs.env["SUPABASE_URL"] = mock
    docs_auth = {
        "Authorization": "Bearer "
        + jwt.encode(
            {
                "sub": user,
                "aud": "authenticated",
                "iss": f"{mock}/auth/v1",
                "exp": int(time.time()) + 3600,
                "email": "smoke@example.com",
            },
            SECRET,
            algorithm="HS256",
        )
    }
    docs.start()
    time.sleep(2)
    docs_report: dict[str, object] = {"startup": mem("smoke-docs")}

    text = "Progressive overload squats deadlifts protein recovery sleep endurance mobility. " * 22
    pdf = make_pdf([f"Page {i}. {text}" for i in range(args.pdf_pages)])
    docs_report["pdf_bytes"] = len(pdf)
    body, ctype = multipart("big-plan.pdf", "application/pdf", pdf)
    code, resp = http(
        "POST",
        f"{docs.url}/api/v1/documents",
        data=body,
        headers={**docs_auth, "Content-Type": ctype},
        timeout=120,
    )
    doc = json.loads(resp)
    docs_report["upload"] = {"code": code, "status": doc.get("status")}

    # Wait until the job has checkpointed part-way, then SIGKILL the container.
    deadline = time.time() + 120
    progress = 0
    while time.time() < deadline:
        rows = db_query(plain, "SELECT status, next_unit, total_units FROM document_ingestion_jobs")
        if rows and rows[0][1] and rows[0][1] >= 25:
            progress = rows[0][1]
            break
        time.sleep(0.3)
    docs_report["killed_at_page"] = progress
    docs_report["peak_before_kill"] = mem("smoke-docs")
    sh("docker", "kill", "smoke-docs")
    row = db_query(
        plain, "SELECT status, next_unit, total_units, attempts FROM document_ingestion_jobs"
    )[0]
    docs_report["job_after_kill"] = {
        "status": row[0],
        "next_unit": row[1],
        "total": row[2],
        "attempts": row[3],
    }
    chunks_at_kill = db_query(
        plain, "SELECT count(*) FROM vector_chunks WHERE collection = 'user_documents'"
    )[0][0]
    docs_report["chunks_at_kill"] = chunks_at_kill

    # "Render restart": same image, fresh process. Lease expires, job resumes.
    sh("docker", "start", "smoke-docs")
    docs.wait()
    end = time.time() + 300
    final = None
    while time.time() < end:
        row = db_query(
            plain,
            "SELECT d.status, j.status, j.next_unit, j.attempts "
            "FROM documents d JOIN document_ingestion_jobs j ON j.document_id = d.id",
        )[0]
        if row[0] == "indexed" or row[1] == "failed":
            final = row
            break
        time.sleep(1)
    docs_report["after_restart"] = (
        {"document": final[0], "job": final[1], "next_unit": final[2], "attempts": final[3]}
        if final
        else "TIMEOUT"
    )
    idx = [
        r[0]
        for r in db_query(
            plain,
            "SELECT (metadata->>'chunk_index')::int FROM vector_chunks "
            "WHERE collection = 'user_documents' ORDER BY 1",
        )
    ]
    docs_report["chunks_total"] = len(idx)
    docs_report["chunk_indices_contiguous_unique"] = idx == list(range(len(idx)))
    docs_report["chunks_survived_kill"] = chunks_at_kill <= len(idx)
    docs_report["peak_after_pdf"] = mem("smoke-docs")

    # Idempotency: a duplicate upload does not create a second document or job.
    code2, resp2 = http(
        "POST",
        f"{docs.url}/api/v1/documents",
        data=body,
        headers={**docs_auth, "Content-Type": ctype},
        timeout=120,
    )
    docs_report["duplicate_upload"] = {"code": code2}
    docs_report["job_rows"] = db_query(plain, "SELECT count(*) FROM document_ingestion_jobs")[0][0]
    docs_report["mock_stats"] = json.loads(http("GET", f"http://localhost:{MOCK_PORT}/stats")[1])
    report["documents"] = docs_report
    docs.stop()
    server.shutdown()

    print(json.dumps(report, indent=2))
    ok = (
        docs_report["after_restart"] != "TIMEOUT"
        and docs_report["chunk_indices_contiguous_unique"]
        and docs_report["chunks_survived_kill"]
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
