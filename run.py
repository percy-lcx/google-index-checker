#!/usr/bin/env python3
"""Start the backend (uvicorn) and frontend (vite) together."""

import os
import signal
import subprocess
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND_DIR = ROOT / "backend"
FRONTEND_DIR = ROOT / "frontend"


def backend_python() -> str:
    venv_py = BACKEND_DIR / "venv" / "bin" / "python"
    return str(venv_py) if venv_py.exists() else sys.executable


def stream_output(proc: subprocess.Popen, prefix: str) -> None:
    for line in proc.stdout:
        sys.stdout.write(f"[{prefix}] {line}")
        sys.stdout.flush()


def start(cmd: list[str], cwd: Path, prefix: str) -> subprocess.Popen:
    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        start_new_session=True,
    )
    threading.Thread(target=stream_output, args=(proc, prefix), daemon=True).start()
    return proc


def stop(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        proc.wait(timeout=10)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except ProcessLookupError:
            pass


def main() -> int:
    backend = start(
        [backend_python(), "-m", "uvicorn", "main:app", "--reload", "--port", "8000"],
        BACKEND_DIR,
        "backend",
    )
    frontend = start(["npm", "run", "dev"], FRONTEND_DIR, "frontend")

    procs = [backend, frontend]
    try:
        while True:
            for p in procs:
                if p.poll() is not None:
                    print(f"\nProcess exited with code {p.returncode}, shutting down.")
                    return p.returncode or 1
            for p in procs:
                try:
                    p.wait(timeout=0.5)
                except subprocess.TimeoutExpired:
                    pass
    except KeyboardInterrupt:
        print("\nShutting down...")
        return 0
    finally:
        for p in procs:
            stop(p)


if __name__ == "__main__":
    sys.exit(main())
