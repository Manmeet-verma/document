#!/usr/bin/env python3
"""Launch the Document Data Extraction System web app.

Usage:
    python3 run.py            # starts server on http://127.0.0.1:8000
    python3 run.py --port 9000
"""
import argparse
import uvicorn

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the document extraction web app")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    print(f"Starting Document Data Extraction System on http://{args.host}:{args.port}")
    uvicorn.run("backend.app:app", host=args.host, port=args.port, reload=False)
