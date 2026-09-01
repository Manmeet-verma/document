#!/usr/bin/env python3
"""Standalone CLI runner: scan system folders for person folders with document
images, extract data with OCR, and write a formatted Excel file.

Usage:
    python3 extract.py                          # scan system folders + data/input
    python3 extract.py /path/to/Main_Folder     # scan one specific folder
    python3 extract.py -v                       # verbose OCR progress
    python3 extract.py -o out.xlsx              # custom output path
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time

BACKEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from core.excel_writer import generate_excel  # noqa: E402
from core.pipeline import process_folder, process_roots  # noqa: E402

SYSTEM_SCAN_DIRS = ("Desktop", "Documents", "Downloads", "Pictures")


def _home_system_roots() -> list[str]:
    home = os.path.expanduser("~")
    roots = [os.path.join(home, d) for d in SYSTEM_SCAN_DIRS]
    return [r for r in roots if os.path.isdir(r)]


def main() -> int:
    parser = argparse.ArgumentParser(description="Process documents and generate Excel")
    parser.add_argument("folder", nargs="?", default=None,
                        help="Main folder containing person subfolders (default: data/input)")
    parser.add_argument("-o", "--output", default=None,
                        help="Output .xlsx path (default: data/output/extracted_data_<ts>.xlsx)")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Show OCR progress in the console")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    project = os.path.dirname(os.path.abspath(__file__))
    output_dir = os.path.join(project, "data", "output")
    os.makedirs(output_dir, exist_ok=True)
    start = time.time()

    def progress(i, total, person, stage):
        if args.verbose:
            print(f"  [{i}/{total}] {person}: {stage}", file=sys.stderr)

    if args.folder:
        roots = [args.folder]
        method = "single folder"
    else:
        roots = _home_system_roots()
        data_input = os.path.join(project, "data", "input")
        os.makedirs(data_input, exist_ok=True)
        roots.append(data_input)
        method = "system folders (Desktop, Documents, Downloads, Pictures) + data/input"

    existing = [r for r in roots if os.path.isdir(r)]
    if not existing:
        print("ERROR: none of the scan folders exist on this machine.")
        return 1

    print(f"Scanning: {method}")
    print("Looking for person folders (folders containing document images)...")
    if args.verbose:
        for r in existing:
            print(f"  root: {r}", file=sys.stderr)

    if len(existing) == 1 and args.folder:
        rows = process_folder(existing[0], progress=progress if args.verbose else None)
    else:
        rows = process_roots(existing, progress=progress if args.verbose else None)

    if not rows:
        print("No person folders found. Put folders containing document images")
        print("anywhere in Desktop, Documents, Downloads, or Pictures.")
        return 1

    out_path = args.output or os.path.join(
        output_dir, f"extracted_data_{time.strftime('%Y%m%d_%H%M%S')}.xlsx"
    )
    generate_excel(rows, out_path)

    elapsed = round(time.time() - start, 1)
    print(f"\nDone. Processed {len(rows)} person(s) in {elapsed}s")
    print(f"Excel saved to: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
