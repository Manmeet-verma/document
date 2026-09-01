"""End-to-end pipeline: scan main folder -> OCR -> classify -> extract -> rows."""

from __future__ import annotations

import logging
import os

from .document_classifier import classify, pair_documents
from .extractor import merge_row
from .ocr_engine import read_image

log = logging.getLogger("doc_extractor.pipeline")

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp", ".heic"}

RESERVED = {
    "__pycache__", ".git", "output", "excel", "node_modules", ".venv", "venv",
    ".config", ".cache", ".local", ".nvm", ".npm", ".opencode", ".vscode",
    ".vscode-shared", ".pip_tmp", ".dotnet", ".var", "site-packages",
    "data", "backend", "core", "static", "__MACOSX",
}

MIN_PERSON_IMAGES = 2


def is_image(name: str) -> bool:
    ext = os.path.splitext(name)[1].lower()
    return ext in IMAGE_EXT


def _folder_image_count(path: str) -> int:
    count = 0
    try:
        for entry in os.listdir(path):
            if is_image(entry):
                count += 1
    except OSError:
        return 0
    return count


def discover_persons(root: str, recursive: bool = True) -> list[str]:
    """Find person folders under a root.

    A person folder is any folder that directly contains at least
    MIN_PERSON_IMAGES document images.
    """
    persons: list[str] = []
    if not os.path.isdir(root):
        return persons

    def walk(path: str):
        base = os.path.basename(path)
        if base in RESERVED:
            return
        if _folder_image_count(path) >= MIN_PERSON_IMAGES:
            persons.append(path)
            return
        if recursive:
            try:
                for entry in sorted(os.listdir(path)):
                    full = os.path.join(path, entry)
                    if os.path.isdir(full):
                        walk(full)
            except OSError:
                pass

    walk(root)
    return sorted(persons)


def process_roots(roots: list[str], progress=None) -> list[dict]:
    """Process person folders found under several root folders."""
    persons: list[str] = []
    seen: set[str] = set()
    for root in roots:
        for p in discover_persons(root):
            key = os.path.realpath(p)
            if key not in seen:
                seen.add(key)
                persons.append(p)
    return process_folders(persons, progress)


def process_folders(persons: list[str], progress=None) -> list[dict]:
    """Run the OCR + extraction pipeline over a concrete list of person folders."""
    total = len(persons)
    rows: list[dict] = []
    for i, person_dir in enumerate(persons, start=1):
        person_id = os.path.basename(person_dir)
        log.info("Processing %s (%d/%d)", person_id, i, total)
        if progress:
            progress(i, total, person_id, "processing")

        images = sorted(
            os.path.join(person_dir, f) for f in os.listdir(person_dir) if is_image(f)
        )
        images.sort(key=lambda p: _sort_key(os.path.basename(p)))

        ocr_items: list[tuple[str, dict]] = []
        for img in images:
            if progress:
                progress(i, total, person_id, f"OCR {os.path.basename(img)}")
            try:
                results = read_image(img)
                text = "\n".join(r["text"] for r in results)
                conf = _avg_conf(results)
            except Exception as exc:
                log.warning("OCR failed for %s: %s", img, exc)
                text, conf = "", 0.0
            doc_type, class_conf = classify(img, text)
            info = {"path": img, "text": text, "conf": conf}
            if class_conf >= 0.5:
                ocr_items.append((doc_type, info))

        pairs = pair_documents(ocr_items)
        row = merge_row(person_id, pairs)
        row["source_folder"] = person_dir
        rows.append(row)
        if progress:
            progress(i, total, person_id, "done")

    return rows


def _sort_key(name: str) -> tuple:
    import re
    lower = name.lower()
    doc = 1 if "rc" in lower or "registration" in lower else 0
    side = 1 if any(k in lower for k in ("back", "reverse", "rear")) else 0
    return (doc, side, name)


def process_folder(main_folder: str, progress=None) -> list[dict]:
    """Process the main folder and return one row dict per person."""
    persons = discover_persons(main_folder)
    total = len(persons)
    rows: list[dict] = []

    for i, person_dir in enumerate(persons, start=1):
        person_id = os.path.basename(person_dir)
        log.info("Processing %s (%d/%d)", person_id, i, total)
        if progress:
            progress(i, total, person_id, "processing")

        images = sorted(
            os.path.join(person_dir, f) for f in os.listdir(person_dir) if is_image(f)
        )
        ocr_items: list[tuple[str, dict]] = []
        for img in images:
            if progress:
                progress(i, total, person_id, f"OCR {os.path.basename(img)}")
            try:
                results = read_image(img)
                text = "\n".join(r["text"] for r in results)
                conf = _avg_conf(results)
            except Exception as exc:
                log.warning("OCR failed for %s: %s", img, exc)
                text, conf = "", 0.0
            doc_type, class_conf = classify(img, text)
            info = {"path": img, "text": text, "conf": conf}
            if class_conf >= 0.5:
                ocr_items.append((doc_type, info))

        pairs = pair_documents(ocr_items)
        row = merge_row(person_id, pairs)
        row["source_folder"] = person_dir
        rows.append(row)
        if progress:
            progress(i, total, person_id, "done")

    return rows


def _avg_conf(results: list[dict]) -> float:
    if not results:
        return 0.0
    return sum(r["conf"] for r in results) / len(results)
