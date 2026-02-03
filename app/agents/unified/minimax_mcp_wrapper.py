"""STDIO wrapper for Minimax MCP server.

Filters out non-JSON lines on stdout so the MCP client doesn't choke on
startup banners (e.g., "Starting Minimax MCP server").
"""
from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import threading
from typing import List


def _get_real_command() -> str:
    cmd = (os.getenv("MINIMAX_MCP_REAL_COMMAND") or "").strip()
    if cmd:
        return cmd
    # Fallback to the current interpreter.
    return sys.executable


def _get_real_args() -> List[str]:
    raw = os.getenv("MINIMAX_MCP_REAL_ARGS")
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                return [str(item) for item in data]
        except Exception:
            pass
    fallback = os.getenv("MINIMAX_MCP_ARGS") or "-m minimax_mcp.server"
    return shlex.split(fallback)


def _forward_stdin(proc: subprocess.Popen[bytes]) -> None:
    if proc.stdin is None:
        return
    try:
        for chunk in iter(lambda: sys.stdin.buffer.read(4096), b""):
            proc.stdin.write(chunk)
            proc.stdin.flush()
    except (BrokenPipeError, OSError):
        return
    finally:
        try:
            proc.stdin.close()
        except Exception:
            pass


def _forward_stderr(proc: subprocess.Popen[bytes]) -> None:
    if proc.stderr is None:
        return
    for chunk in iter(lambda: proc.stderr.readline(), b""):
        if not chunk:
            break
        try:
            sys.stderr.buffer.write(chunk)
            sys.stderr.buffer.flush()
        except Exception:
            break


def _forward_stdout_filtered(proc: subprocess.Popen[bytes]) -> None:
    if proc.stdout is None:
        return
    for line in iter(proc.stdout.readline, b""):
        if not line:
            break
        stripped = line.strip()
        if not stripped:
            continue
        try:
            json.loads(stripped.decode("utf-8"))
        except Exception:
            # Drop non-JSON banner/log lines.
            continue
        try:
            sys.stdout.buffer.write(line)
            sys.stdout.buffer.flush()
        except Exception:
            break


def main() -> int:
    command = _get_real_command()
    args = _get_real_args()
    env = os.environ.copy()

    proc = subprocess.Popen(
        [command, *args],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )

    threads = [
        threading.Thread(target=_forward_stdout_filtered, args=(proc,), daemon=True),
        threading.Thread(target=_forward_stderr, args=(proc,), daemon=True),
        threading.Thread(target=_forward_stdin, args=(proc,), daemon=True),
    ]
    for thread in threads:
        thread.start()

    return proc.wait()


if __name__ == "__main__":
    raise SystemExit(main())
