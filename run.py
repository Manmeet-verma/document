#!/usr/bin/env python3
"""Launch the Document Data Extraction System web app.

Usage:
    python3 run.py            # starts server on http://127.0.0.1:8000
    python3 run.py --port 9000
"""
import argparse
import os
from pathlib import Path

import uvicorn


def _load_env():
    env_file = Path(__file__).resolve().parent / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


if __name__ == "__main__":
    _load_env()
    parser = argparse.ArgumentParser(description="Run the document extraction web app")
    parser.add_argument(
        "--host",
        default=os.environ.get("HOST", "127.0.0.1"),
        help="host to bind (env: HOST)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("PORT", "8000")),
        help="port to bind (env: PORT)",
    )
    args = parser.parse_args()
    print(f"Starting Document Data Extraction System on http://{args.host}:{args.port}")
    uvicorn.run("backend.app:app", host=args.host, port=args.port, reload=False)
